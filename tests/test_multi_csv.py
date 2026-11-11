import asyncio
from pathlib import Path
import tempfile
import unittest
from harness.agents.multi_csv import select_csv_inputs, describe_csv, solve_multi_csv_task
from harness.config import TaskContext

class MultiCSVControls(unittest.TestCase):
    def test_selection_requires_two_existing_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ("a.csv","b.csv","c.csv"): (root/name).write_text("key\nx\n")
            self.assertEqual([p.name for p in select_csv_inputs(root,"Read a.csv and b.csv.")],["a.csv","b.csv"])
            for instruction in ("Total all tables","Read a.csv and missing.csv.","Read ../a.csv and b.csv.","Read a.csv b.csv c.csv."):
                self.assertIsNone(select_csv_inputs(root,instruction))
    def test_preview_uses_csv_records_and_preserves_strings(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"a.csv"
            path.write_text('key,value\n01,"hello\nworld"\n2,x\n3,y\n4,z\n',encoding="utf-8",newline="")
            data=describe_csv(path)
            self.assertEqual(data["rows"],4)
            self.assertEqual(len(data["sample_rows"]),3)
            self.assertEqual(data["sample_rows"][0],{"key":"01","value":"hello\nworld"})
    def test_ambiguous_or_malformed_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"a.csv"
            for content in ("x,x\n1,2\n","x,y\n1\n","x\n1,2\n"):
                path.write_text(content)
                with self.assertRaises(ValueError): describe_csv(path)

class MultiCSVExecutionControls(unittest.IsolatedAsyncioTestCase):
    async def invoke(self,root,code,instruction="Read a.csv and b.csv and sum x from a.csv."):
        class Bridge:
            async def complete(self,**kwargs):
                assert kwargs["max_tokens"]==400
                return code,20,10,0
        return await solve_multi_csv_task(TaskContext("csv","data_analysis",instruction,2,root,root,900,False),Bridge())
    async def test_real_execution_uses_all_rows_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            original="x\n1\n2\n3\n100\n"
            (root/"a.csv").write_text(original)
            (root/"b.csv").write_text("y\n1\n")
            result=await self.invoke(root,'import csv\nprint(sum(int(r["x"]) for r in csv.DictReader(open("a.csv"))))')
            self.assertEqual((result.status,result.answer),("SOLVED","106"))
            self.assertEqual((root/"a.csv").read_text(),original)
    async def test_mutation_and_multiple_answers_retain_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ("a.csv","b.csv"): (root/name).write_text("x\n1\n")
            for code,status in (('open("a.csv","w").write("bad"); print(7)',"UNKNOWN"),('print(1);print(2)',"FAILED")):
                result=await self.invoke(root,code)
                self.assertEqual(result.status,status)
                self.assertEqual(result.effective_cost,12)
                self.assertEqual((root/"a.csv").read_text(),"x\n1\n")
    async def test_missing_input_does_not_call_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ("a.csv","b.csv"): (root/name).write_text("x\n1\n")
            class Bridge:
                async def complete(self,**kwargs): raise AssertionError("No request allowed")
            result=await solve_multi_csv_task(TaskContext("csv","data_analysis","Read a.csv and absent.csv.",2,root,root,900,False),Bridge())
            self.assertEqual(result.status,"UNKNOWN")

    async def test_existing_named_single_source_fast_path_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"a.csv").write_text("product,month,units\nwidget,1,999\n")
            (root/"b.csv").write_text("product,month,units\nwidget,1,7\n")
            class Bridge:
                async def complete(self,**kwargs): raise AssertionError("Fast path must remain free")
            instruction="The file b.csv has columns product,month,units (1 rows). How many units of product 'widget' were sold in months 1 through 1 inclusive?"
            result=await solve_multi_csv_task(TaskContext("csv","data_analysis",instruction,2,root,root,900,False),Bridge())
            self.assertEqual((result.status,result.answer),("SOLVED","7"))
