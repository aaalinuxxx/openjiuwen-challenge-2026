import copy
import csv
import io
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest

from harness.agents.join_plans import execute_join_plan,parse_join_plan,solve_join_plan_task
from harness.config import TaskContext

ROOT=Path(__file__).resolve().parents[1]

def write_csv(path,rows):
    with path.open("w",newline="",encoding="utf-8") as file:
        writer=csv.writer(file)
        writer.writerow(["key","value","tag"])
        writer.writerows(rows)

def plan(join="inner",side="left",op="sum",filt=None):
    return dict(left="a.csv",right="b.csv",left_key="key",right_key="key",join=join,filter=filt,
                aggregate=dict(op=op,side=side if op=="sum" else None,column="value" if op=="sum" else None))

class JoinPlanControls(unittest.TestCase):
    def test_frozen_gold_plans(self):
        cases=json.loads((ROOT/"experiments/E65_join_plan/cases.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for case in cases:
                if case["gold_plan"] is None: continue
                selected=[]
                for name,content in case["files"].items():
                    path=root/name
                    path.write_text(content,encoding="utf-8")
                    selected.append(path)
                self.assertEqual(execute_join_plan(case["gold_plan"],selected),case["expected"])

    def test_randomized_sqlite_equivalence(self):
        rng=random.Random(6509)
        comparisons=0
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for sample in range(12):
                data={side:[(rng.choice(["01","1","A"]),str(rng.randrange(-3,8)),rng.choice(["keep","drop"]))
                            for _ in range(rng.randrange(7))] for side in ("left","right")}
                write_csv(root/"a.csv",data["left"]); write_csv(root/"b.csv",data["right"])
                with sqlite3.connect(":memory:") as db:
                    for table,side in (("a","left"),("b","right")):
                        db.execute("CREATE TABLE "+table+" (key TEXT,value TEXT,tag TEXT)")
                        db.executemany("INSERT INTO "+table+" VALUES (?,?,?)",data[side])
                    for join in ("inner","left","anti"):
                        for aggregate in ("count","left","right"):
                            if join=="anti" and aggregate=="right": continue
                            for filtered in ([False] if join=="anti" else [False,True]):
                                filt=dict(side="right",column="tag",equals="keep") if filtered else None
                                p=plan(join,aggregate,"count" if aggregate=="count" else "sum",filt)
                                select="COUNT(*)" if aggregate=="count" else "COALESCE(SUM(CAST("+("a" if aggregate=="left" else "b")+".value AS INTEGER)),0)"
                                if join=="anti":
                                    query="SELECT "+select+" FROM a WHERE NOT EXISTS (SELECT 1 FROM b WHERE a.key=b.key)"
                                else:
                                    query="SELECT "+select+" FROM a "+("LEFT JOIN" if join=="left" else "JOIN")+" b ON a.key=b.key"
                                    if filtered: query+=" WHERE b.tag='keep'"
                                expected=str(db.execute(query).fetchone()[0])
                                self.assertEqual(execute_join_plan(p,[root/"a.csv",root/"b.csv"]),expected,(sample,p))
                                comparisons+=1
        self.assertEqual(comparisons,168)

    def test_exact_decimal_sum_and_left_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            write_csv(root/"a.csv",[("x","0.1","keep"),("x","0.2","keep"),("z","9","keep")])
            write_csv(root/"b.csv",[("x","0.3","keep"),("x","0.4","keep")])
            self.assertEqual(execute_join_plan(plan(),[root/"a.csv",root/"b.csv"]),"0.6")
            self.assertEqual(execute_join_plan(plan("left","right"),[root/"a.csv",root/"b.csv"]),"1.4")

    def test_bad_fields_and_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            write_csv(root/"a.csv",[("x","1","keep")]); write_csv(root/"b.csv",[("x","2","keep")])
            variants=[]
            for key,value in (("left","../a.csv"),("right","a.csv"),("join","full"),("left_key","missing"),("extra",1)):
                p=plan();p[key]=value;variants.append(p)
            p=plan();p["aggregate"]["op"]="median";variants.append(p)
            p=plan();p["filter"]={"side":"right","column":"tag","equals":"keep","numeric_gt":5};variants.append(p)
            for p in variants:
                with self.assertRaises(ValueError): execute_join_plan(p,[root/"a.csv",root/"b.csv"])

    def test_bad_csv_numbers_empty_keys_and_pair_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            write_csv(root/"b.csv",[("x","2","keep"),("x","3","keep")])
            for key,value in (("x","NaN"),("x","not-a-number"),("","1")):
                write_csv(root/"a.csv",[(key,value,"keep")])
                with self.assertRaises(ValueError): execute_join_plan(plan(),[root/"a.csv",root/"b.csv"])
            write_csv(root/"a.csv",[("x","1","keep")])
            with self.assertRaises(ValueError): execute_join_plan(plan(),[root/"a.csv",root/"b.csv"],max_pairs=1)
            (root/"a.csv").write_text("key,key\nx,x\n")
            with self.assertRaises(ValueError): execute_join_plan(plan(),[root/"a.csv",root/"b.csv"])

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        with self.assertRaises(ValueError): parse_join_plan('{"join":"inner","join":"anti"}')
        self.assertIsNone(parse_join_plan("UNSUPPORTED"))

class JoinPlanUsageControls(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_or_unsupported_plan_retains_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            write_csv(root/"a.csv",[("x","1","keep")]); write_csv(root/"b.csv",[("x","2","keep")])
            for text in ("UNSUPPORTED","not-json",'{"left":"a.csv"}'):
                class Bridge:
                    async def complete(self,**kwargs): return text,20,10,0
                result=await solve_join_plan_task(TaskContext("plan","data_analysis","Read a.csv and b.csv.",2,root,root,1000,False),Bridge())
                self.assertEqual(result.status,"UNKNOWN")
                self.assertEqual(result.effective_cost,12)
