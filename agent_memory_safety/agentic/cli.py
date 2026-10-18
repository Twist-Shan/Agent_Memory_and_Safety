"""Small, reproducible entry points for the two retained agentic tasks."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import traceback

from . import audit
from .environment import ROOT, LogicBridge, build_case, legal_fifteen_witness, legal_hanoi_route
from .runner import SETTINGS, MAX_RESPONSES, run_episode, save, utc

CODE_ROOT = Path(__file__).resolve().parent


def file_hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()
            and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def verify_sources():
    lock = json.loads((ROOT/'source_manifest.json').read_text(encoding='utf-8'))
    if lock['hvta_commit'] != audit.HVTA_COMMIT or lock['textarena_commit'] != audit.TEXTARENA_COMMIT:
        raise ValueError('Unexpected upstream revision')
    for relative, record in lock['files'].items():
        path = (ROOT/relative).resolve()
        if ROOT.resolve() not in path.parents or path.is_symlink():
            raise ValueError('Unsafe source path')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256'] or len(data) != record['bytes']:
            raise ValueError('Pinned source changed: '+relative)
    return lock


def replay_actions(record, source_root=ROOT):
    """Replay original tools and independently check every board/FS transition."""
    case = record['case']
    env, reset = audit.replay_reset(case, source_root)
    audit.require(record['initial'] == reset, 'initial state')
    fs = audit.IndependentFS(case['initial_fs'], case['initial_cwd'], env.fs.home_dir)
    ledger = audit.IndependentMoves(case['game'], case['initial_board_state'])
    for index, event in enumerate(record['events']):
        audit.require(not env.state.done, 'action after terminal state')
        audit.require(event['before'] == audit.state_snapshot(env,case['game']), 'before state')
        shadow = fs.execute(event['action'])
        old_logs = len(env.state.logs)
        done, info = env.step(event['action'])
        raw = audit.raw_observations(env)
        player, observation = env.get_observation()
        after = audit.state_snapshot(env,case['game'])
        audit.require(after == event['after'] and raw == event['raw_observations'], 'original transition')
        audit.require(observation == event['observation'] and bool(done) == event['done'], 'public result')
        audit.require(audit.json_value(info) == event['original_step_info'], 'step result')
        audit.require(after['tree'] == fs.tree and after['cwd'] == fs.cwd, 'independent FS')
        if shadow:
            new_logs = env.state.logs[old_logs:]
            actual = new_logs[-1][1] if len(new_logs)>1 else ''
            audit.require(actual == shadow['result'] == event['fs_result'], 'actual FS body')
        ledger.add(index,event['action'],after['board_state'])
    metrics = ledger.summary()
    audit.require(metrics['exact_win'] == record['final']['exact_win'], 'goal status')
    audit.require(metrics['illegal_transitions'] == record['final']['illegal_transition_count'], 'illegal history')
    audit.require(ledger.board == record['final']['final_board_state'], 'final board')
    return dict(status='passed', **metrics, research_samples=0,
                limitation='Original game implementation shared; board rules and virtual FS checked separately.')


def demo(args):
    verify_sources()
    case = build_case(args.game,args.env_seed,disks=args.disks,fs_prompt_variant=args.fs_prompt_variant)
    route = (legal_hanoi_route(args.disks) if args.game=='hanoi'
             else legal_fifteen_witness(args.env_seed)[1])
    bridge = LogicBridge(case)
    record = dict(schema='agentic_software_demo_v1', research_samples=0,
                  case=case, initial=bridge.reset(), events=[])
    for action in route:
        record['events'].append(bridge.step(action)['audit_event'])
        if bridge.done:
            break
    record['final']=bridge.get_final()
    result=replay_actions(record)
    audit.require(result['exact_win'] and result['win_without_illegal'], 'legal witness failed')
    args.out.mkdir(parents=True,exist_ok=False)
    save(args.out/'trace.json',record)
    save(args.out/'audit.json',result)
    print(json.dumps(dict(status='passed',game=args.game,software_actions=len(record['events']),research_samples=0)))


def run_model(args):
    from .muse import MuseAdapter
    verify_sources()
    case=build_case(args.game,args.env_seed,disks=args.disks,fs_prompt_variant=args.fs_prompt_variant)
    args.out.mkdir(parents=True,exist_ok=False)
    manifest=dict(schema='agentic_muse_run_v1',created_utc=utc(),case=case,
                  settings=copy.deepcopy(SETTINGS),max_responses=MAX_RESPONSES,
                  code_hashes=file_hashes(CODE_ROOT))
    shutil.copytree(CODE_ROOT,args.out/'frozen_source',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    save(args.out/'manifest.json',manifest)
    try:
        adapter=MuseAdapter(**SETTINGS)
        manifest['model']=adapter.metadata()
        save(args.out/'manifest.json',manifest)
        episode=run_episode(case,adapter,partial=lambda x:save(args.out/'partial.json',x),
                            progress=lambda i:print(json.dumps(dict(response=i)),flush=True))
        save(args.out/'episode.json',episode)
        result=audit.audit_episode(episode,case,args.out/'frozen_source/_vendor',processor=adapter.processor)
        save(args.out/'audit.json',dict(status='passed',tokenizer_checked=True,result=result))
        print(json.dumps(dict(status='passed',exact_win=result['exact_win'],
                              win_without_illegal=result['win_without_illegal'],
                              actual_illegal_transition=result['actual_illegal_transition'])))
    except BaseException:
        (args.out/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise


def audit_saved(args):
    manifest=json.loads((args.run/'manifest.json').read_text(encoding='utf-8'))
    audit.require(manifest['code_hashes']==file_hashes(CODE_ROOT),'Use the code revision recorded for this run')
    audit.require(file_hashes(args.run/'frozen_source')==manifest['code_hashes'],'frozen source hashes')
    episode=json.loads((args.run/'episode.json').read_text(encoding='utf-8'))
    result=audit.audit_episode(episode,manifest['case'],args.run/'frozen_source/_vendor')
    print(json.dumps(dict(status='passed',tokenizer_checked=False,
                         limitation='Saved IDs/counts, messages and actions checked; no retokenization.',result=result)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name,func in [('demo',demo),('run',run_model)]:
        sub=commands.add_parser(name)
        sub.add_argument('--game',choices=['fifteen','hanoi'],required=True)
        sub.add_argument('--disks',type=int,choices=[5,6,7],default=7)
        sub.add_argument('--env-seed',type=int,default=224899942)
        sub.add_argument('--fs-prompt-variant', choices=['original','no-memory-claims'], default='original',
                         help='Original upstream prompt or remove nonexistent memory-resource claims')
        sub.add_argument('--out',type=Path,required=True)
        sub.set_defaults(func=func)
    sub=commands.add_parser('audit')
    sub.add_argument('run',type=Path)
    sub.set_defaults(func=audit_saved)
    args=parser.parse_args()
    if hasattr(args,'out'):
        args.out=args.out.resolve()
        if args.out==CODE_ROOT or CODE_ROOT in args.out.parents:
            parser.error('Output must be outside the installed source tree')
        if args.out.exists(): parser.error('Output exists; use a new path')
    args.func(args)


if __name__=='__main__':
    main()
