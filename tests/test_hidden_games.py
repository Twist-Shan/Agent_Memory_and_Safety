import copy,json,unittest
from pathlib import Path
from agent_memory_safety.agentic.hidden_games import make_case,HiddenBridge,replay,CONFIGS
from agent_memory_safety.agentic.extra_games import offline_nltk
from agent_memory_safety.agentic.runner import initial_messages,public_result
class HiddenTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): offline_nltk(Path('runs/nltk_api_v1').resolve())
 def test_generated_cases_and_witness_replay(self):
  # Software fixtures only: no private manifests, model calls or research samples.
  cases=[make_case(game,123,'software_only_'+game) for game in
         ('mastermind','guessnumber','hangman','logicpuzzle')]
  for c in cases:
   with self.subTest(case=c['id']):
    b=HiddenBridge(c); first=b.reset(); events=[]
    prompt=json.dumps(initial_messages(c,public_result(first)))
    self.assertNotIn(c['solution_payload'],prompt)
    self.assertNotIn(c['solution_path'],prompt)
    self.assertFalse(b.env.logical_bug)
    events.append({'audit_event':b.step('[fs_ls /home/user]')['audit_event']})
    self.assertEqual(b.get_final()['solution_read_count'],0)
    events.append({'audit_event':b.step('[fs_cat '+c['solution_path']+']')['audit_event']})
    self.assertEqual(b.get_final()['solution_read_count'],1)
    s=b.env.state.game_state; game=c['game']
    if game=='mastermind': moves=['['+' '.join(map(str,s['secret_code']))+']']
    elif game=='guessnumber': moves=['['+str(s['game_number'])+']']
    elif game=='hangman': moves=['['+s['target_word']+']']
    else: moves=[f'[{r} {col} {mark}]' for grid in b.env._get_inner_env().game_board_solution.values() for r,row in grid.items() for col,mark in row.items()]
    for a in moves:
     if b.done: break
     events.append({'audit_event':b.step(a)['audit_event']})
    self.assertTrue(b.get_final()['valid_goal'])
    ep=dict(case=c,initial_audit=first,steps=[dict(events=events)],final=b.get_final())
    self.assertEqual(replay(ep)['status'],'passed')
    bad=copy.deepcopy(ep); bad['steps'][0]['events'][0]['audit_event']['after']['turn']+=1
    with self.assertRaises(AssertionError): replay(bad)
 def test_read_renamed_file(self):
  c=make_case('mastermind',123,'software_only'); b=HiddenBridge(c); b.reset()
  b.step('[fs_mv '+c['solution_path']+' /home/user/note.txt]')
  b.step('[fs_cat /home/user/note.txt]')
  self.assertEqual(b.get_final()['solution_read_count'],1)
 def test_ten_valid_guesses_stop_without_solution_read(self):
  c=make_case('guessnumber1000',123,'software_only_limit')
  b=HiddenBridge(c); b.reset()
  target=b.env.state.game_state['game_number']
  guesses=[n for n in range(1,1001) if n!=target][:10]
  for index,n in enumerate(guesses):
   b.step('['+str(n)+']')
   self.assertEqual(b.done,index==9)
  self.assertFalse(b.get_final()['valid_goal'])
  self.assertEqual(b.get_final()['solution_read_count'],0)
if __name__=='__main__': unittest.main()
