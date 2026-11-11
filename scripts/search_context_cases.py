"""Freeze search context controls without importing production search code."""
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'experiments'/'E47_search_context'
BASE={
    'a.md':'# Mira Vale\nMentor: Oren Pike\nBorn: 1990\n',
    'b.md':'# Oren Pike\nEmployer: Luma Labs\n',
    'c.md':'# Luma Labs\nHeadquarters: Riga\n',
    'd.md':'# Unrelated Corp\nHeadquarters: Perth\n'}
CASES=[]
def add(name,files,question,**checks):
    CASES.append(dict(name=name,files=files,question=question,reply='UNSOLVABLE',checks=checks))
add('chain_paraphrase',BASE,
    'Return the headquarters city of the company employing the mentor of Mira Vale.',
    required_values=['Mira Vale','Oren Pike','Luma Labs','Riga'],expected_status='UNKNOWN')
add('cycle',dict(BASE,**{'b.md':'# Oren Pike\nEmployer: Luma Labs\nMentor: Mira Vale\n'}),
    'Using the records about Mira Vale, return the city of her mentor employer.',
    required_values=['Luma Labs','Riga'],expected_status='UNKNOWN',max_records=32)
add('casefold_links',dict(BASE,**{'a.md':'# Mira Vale\nMentor: OREN PIKE\n','b.md':'# Oren Pike\nEmployer: luma labs\n'}),
    'Return the headquarters of the employer of the mentor of MIRA VALE.',
    required_values=['Luma Labs','Riga'],expected_status='UNKNOWN')
add('prefix_decoy',{'a.md':'# Ann\nBorn: 9999\n','b.md':'# Anne\nBorn: 1988\n'},
    'Tell me the birth year of Anne.',
    required_values=['Anne','1988'],forbidden_values=['9999'],expected_status='UNKNOWN')
branches={'root.md':'# Hub\n'+''.join(f'Relation{i}: Node {i:02d}\n' for i in range(40))}
branches.update({f'node_{i:02d}.md':f'# Node {i:02d}\nValue: {i}\n' for i in range(40)})
add('node_cap',branches,'Summarize a fact connected to Hub.',max_records=32,expected_status='UNKNOWN')
add('oversized_card',{'a.md':'# Huge Person\nBiography: '+'X'*13000+'\nBorn: 1982\n'},
    'Tell me a fact about Huge Person.',max_context_bytes=12000,expected_status='UNKNOWN',expected_calls=0)
add('no_anchor_large',{f'{i}.md':f'# Item {i:02d}\nValue: {i}\n' for i in range(40)},
    'Give the unavailable value for someone not mentioned here.',max_records=32,expected_status='UNKNOWN')
add('full_kb_refusal',{'a.md':'# Ada\nBorn: 1991\n'},
    'Who founded Unknown Corporation? Use only these records.',expected_status='UNSOLVABLE')
conflict={'a.md':'# Nia Moss\nEmployer: Delta Works\nBorn: 1980\n',
          'b.md':'# Nia Moss\nEmployer: Beacon Labs\nBorn: 1980\n',
          'c.md':'# Delta Works\nHeadquarters: Bern\n',
          'd.md':'# Beacon Labs\nHeadquarters: Oslo\n'}
add('conflicting_links',conflict,'Return the city of the employer of Nia Moss.',
    required_values=['Delta Works','Beacon Labs','Bern','Oslo'],expected_status='UNSOLVABLE')
unrelated={'a.md':'# Nia Moss\nBorn: 1980\nEmployer: Delta Works\n',
           'b.md':'# Nia Moss\nBorn: 1981\nEmployer: Delta Works\n',
           'c.md':'# Delta Works\nHeadquarters: Bern\n'}
add('irrelevant_field_conflict',unrelated,"In which city is the headquarters of Nia Moss's employer?",
    expected_status='SOLVED',expected_answer='Bern',expected_calls=0)
add('relevant_field_conflict',unrelated,'In which year was Nia Moss born?',
    expected_status='UNKNOWN',expected_calls=0)
add('finite_cycle_local',{'a.md':'# Ada\nMentor: Bela\nBorn: 1991\n',
    'b.md':'# Bela\nMentor: Ada\n'}, "In which year was Ada's mentor's mentor born?",
    expected_status='SOLVED',expected_answer='1991',expected_calls=0)

if __name__=='__main__':
    DEST.mkdir(parents=True,exist_ok=False)
    (DEST/'cases.json').write_text(json.dumps(CASES,ensure_ascii=False,indent=2),encoding='utf-8')
    plan=dict(created_at=datetime.now(timezone.utc).isoformat(),baseline='bef716967ae2643804b01b9240bc53cb22385414',
        hypotheses=['H03.2 bounded transitive KB context','H03.4 only conflicts on required fields block local proof'],
        api_calls=0,scope='targeted deterministic structural controls; no LLM quality claim',
        controls=len(CASES),before_after='same frozen inputs and fixed refusal response',
        candidate_limits=dict(max_hops=3,max_records=32,max_context_utf8_bytes=12000),
        acceptance='Required facts retained, no prefix decoy, context bounds hold, incomplete-context refusal is UNKNOWN, relevant conflicts remain unresolved.',
        exclusions='No actual model success rate, no universal free-form proof, no provider billing reconciliation')
    (DEST/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(plan))
