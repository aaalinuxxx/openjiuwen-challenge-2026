"""Expose a known semantic limitation; never counts as a successful control."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.agents.search_evidence import verify_evidence
entities={
 'Robin':{'mentor':'Alex','employer':'Birch'},
 'Alex':{'employer':'Cedar'},
 'Birch':{'mentor':'Dara'},
 'Cedar':{'headquarters':'Turku'},
 'Dara':{'headquarters':'Split'},
}
question='Give the headquarters city of the mentor of the employer of Robin.'
proposal=dict(status='SOLVED',answer='Turku',evidence=[
 ['Robin','mentor'],['Alex','employer'],['Cedar','headquarters']])
result=verify_evidence(question,entities,tuple(entities),True,proposal)
report=dict(scope='Adversarial local scope probe; no API',api_calls=0,
 question=question,entities=entities,model_proposal=proposal,
 correct_answer='Split',correct_path=[['Robin','employer'],['Birch','mentor'],['Dara','headquarters']],
 validator_result=dict(status=result[0],answer=result[1],notes=result[2]),
 semantic_check_passed=result[0]!='SOLVED' or result[1]=='Split',
 conclusion='Existing connected facts and relation counts do not prove relationship order in the question',
 blocks_general_semantic_validation_claim=True)
(ROOT/'experiments/E55_scope_counterexample.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(semantic_check_passed=report['semantic_check_passed'],status=result[0],accepted_answer=result[1],correct_answer='Split')))
