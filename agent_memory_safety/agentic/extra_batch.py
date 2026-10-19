"""Freeze and run 5 cases per additional HVTA game; master/API seed 123."""
from __future__ import annotations
import argparse
import json
import random
import shutil
import traceback
from pathlib import Path
from .cli import CODE_ROOT, file_hashes, verify_sources
from .extra_games import CONFIGS, ExtraBridge, make_case, offline_nltk, replay
from .openrouter import MODEL, OpenRouterAdapter
from .runner import run_episode, save, utc

def prepare(out, resources):
    if out.exists(): raise FileExistsError(out)
    verify_sources()
    offline_nltk(resources)
    rng=random.Random(123)
    seeds=[rng.randrange(2**31) for _ in range(5)]
    cases=[make_case(game,seed,f'{game}_{i:03d}') for game in CONFIGS for i,seed in enumerate(seeds)]
    out.mkdir(parents=True)
    shutil.copytree(CODE_ROOT,out/'frozen_source',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(resources,out/'nltk_data')
    manifest=dict(schema='hvta_extra_api15_v1',created_utc=utc(),model=MODEL,
        master_seed=123,environment_seeds=seeds,cases=cases,code_hashes=file_hashes(CODE_ROOT),
        resource_hashes=file_hashes(out/'nltk_data'),
        settings=dict(temperature=0.7,top_p=0.9,top_k=0,api_seed_per_request=123,
                      reasoning_effort='low',max_tokens_per_response=16384,max_responses=220),
        condition='logical_bug_only',hidden_solution=False,activations=False,
        limitations=['API is not native model replication; provider revision/template unverified.',
                     'No history trimming, response repair, automatic retry or model fallback.',
                     'Minesweeper generates mines on first click; seed alone does not fix its board.',
                     'Five seeds are fixed without outcome filtering; duplicate instances are reported, never replaced.',
                     'Original NLTK download calls resolved to frozen local resources; no source edits.',
                     'Same upstream game code used for replay, with separate bug/valid-goal checks.'])
    save(out/'manifest.json',manifest)
    print(json.dumps(dict(status='prepared',cases=len(cases),seeds=seeds)))

def run(out, game, env_file):
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['code_hashes']==file_hashes(CODE_ROOT)==file_hashes(out/'frozen_source'), 'Source drift'
    assert manifest['resource_hashes']==file_hashes(out/'nltk_data'), 'Resource drift'
    verify_sources(); offline_nltk(out/'nltk_data')
    key=next(line.split('=',1)[1].strip().strip('\"').strip("'") for line in env_file.read_text(encoding='utf-8-sig').splitlines() if line.startswith('OPENROUTER_API_KEY='))
    if not key: raise ValueError('Empty credential')
    shard=out/game
    shard.mkdir(exist_ok=False) # launch-once guard, including partially failed starts
    with (shard/'launch_once.json').open('x',encoding='utf-8') as f:
        json.dump(dict(started_utc=utc(),game=game),f)
    results=[]
    for case in [c for c in manifest['cases'] if c['game']==game]:
        case_out=shard/case['id']; case_out.mkdir()
        save(case_out/'case.json',case)
        save(shard/'status.json',dict(status='running',case=case['id'],completed=len(results)))
        try:
            snapshot_index=0
            (case_out/'snapshots').mkdir()
            def snapshot(value):
                nonlocal snapshot_index
                with (case_out/'snapshots'/f'{snapshot_index:04d}.json').open('x',encoding='utf-8') as stream:
                    json.dump(value,stream,ensure_ascii=False,allow_nan=False)
                snapshot_index+=1
            episode=run_episode(case,OpenRouterAdapter(key,case_out),partial=snapshot,bridge_factory=ExtraBridge)
            save(case_out/'episode.json',episode)
            check=replay(episode); save(case_out/'action_audit.json',check)
            usages=[s['response']['raw_api_response'].get('usage',{}) for s in episode['steps']]
            costs=[u.get('cost') for u in usages]
            result=dict(case=case['id'],termination=episode['termination'],responses=len(usages),
                final={k:v for k,v in episode['final'].items() if k!='state'},
                cost_usd=sum(costs) if all(isinstance(c,(int,float)) for c in costs) else None,
                provider_reported_usage=usages,replay_status=check['status'])
            save(case_out/'result.json',result); results.append(result)
            print(json.dumps(dict(case=case['id'],completed=len(results),final=result['final'])),flush=True)
        except BaseException:
            (case_out/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            save(shard/'status.json',dict(status='failed',case=case['id'],completed=len(results),no_retry=True))
            raise
    assert manifest['code_hashes']==file_hashes(CODE_ROOT), 'Source changed during run'
    save(shard/'results.json',results)
    save(shard/'status.json',dict(status='completed',completed=len(results),finished_utc=utc()))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','run'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--resources',type=Path,default=Path('runs/nltk_api_v1'))
    p.add_argument('--game',choices=list(CONFIGS))
    p.add_argument('--env-file',type=Path,default=Path('.env.local'))
    a=p.parse_args(); out=a.out.resolve()
    if out==CODE_ROOT or CODE_ROOT in out.parents: p.error('Output inside source')
    if a.command=='prepare': prepare(out,a.resources.resolve())
    else:
        if not a.game: p.error('--game required')
        run(out,a.game,a.env_file)

if __name__=='__main__': main()
