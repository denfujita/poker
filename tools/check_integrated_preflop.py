from pathlib import Path
from types import SimpleNamespace as NS
import sys,itertools
sys.dont_write_bytecode=True
ns={'__name__':'preflop_policy','__file__':str(Path(sys.argv[1]).resolve())}
exec(compile(Path(sys.argv[1]).read_text(),sys.argv[1],'exec'),ns)
from poker_agent_protocol.game import LegalAction,Seat,Event,BlindLevel
ctx=ns['preflop_context'];act=ns['preflop_action'];pct=lambda cards:ns['_PREFLOP_COMBOS'][''.join(sorted(cards))][0]
def state(n=8,button=5,hero=0,depth=100,history=(),bets=None,stacks=None,statuses=None,to_call=20,pot=30):
 bets=bets or {6:10,7:20};stacks=stacks or {};statuses=statuses or {}
 seats=tuple(Seat(i,stacks.get(i,depth*20-bets.get(i,0)),bets.get(i,0),statuses.get(i,'active')) for i in range(n))
 h=seats[hero];legal=[LegalAction('check')] if not to_call else [LegalAction('fold'),LegalAction('call')]
 if h.stack>to_call:legal.append(LegalAction('raise',max(40,max(s.bet for s in seats)*2-h.bet),h.bet+h.stack))
 s=NS(phase='betting',board=(),cards=('As','Kd','Qh'),seats=seats,button=button,seat=hero,history=tuple(history),blinds=BlindLevel(10,20),to_call=to_call,pot=pot,legal_actions=tuple(legal))
 s.hand_number=1
 s.can=lambda k:next((a for a in s.legal_actions if a.kind==k),None)
 return s
checks=0
def check(x):
 global checks
 assert x,checks
 checks+=1
for i,p in enumerate(('UTG','UTG1','LJ','HJ','CO','BTN','SB','BB')):check(ctx(state(hero=i))['position']==p)
check(ctx(state(hero=5,statuses={0:'folded',1:'folded'}))['position']=='BTN')
s=state(n=2,button=0,hero=0,bets={0:10,1:20});check(ctx(s)['position']=='SB');s.seat=1;check(ctx(s)['position']=='BB')
s=state(hero=5,statuses={1:'busted',3:'busted'},stacks={1:0,3:0});check(ctx(s)['players']==6 and ctx(s)['position']=='BTN')
s=state();s.blinds=BlindLevel(50,100);check(ctx(s)['bb']==100)
for cards in [('As','Ah','Kd'),('2s','3h','7d'),('Ts','9s','8s')]:
 vals=[pct(c) for c in itertools.permutations(cards)];check(None not in vals and len(set(vals))==1)
check(len(ns['_PREFLOP_COMBOS'])==22100)
check(act(state(hero=0),.30).kind=='fold');check(act(state(hero=5),.30).amount==50)
check(act(state(hero=5,depth=30),.30).amount==44);check(act(state(hero=6,to_call=10),.20).amount==50)
check(act(state(hero=7,to_call=0),.99).kind=='check')
h=(Event('blind',6,10),Event('blind',7,20),Event('call',0,20))
s=state(hero=5,history=h,bets={0:20,6:10,7:20},pot=50);check(ctx(s)['pot_class']=='limped');check(act(s,.10).amount==70)
check(act(state(hero=5,depth=8),.20).amount==160);check(act(state(hero=5,depth=8),.95).kind=='fold')
h=(Event('blind',6,10),Event('blind',7,20),Event('raise',0,100))
s=state(hero=5,history=h,bets={0:100,6:10,7:20},stacks={0:0},statuses={0:'all_in'},to_call=100,pot=130)
check(ctx(s)['pot_class']=='all_in' and ctx(s)['facing_bb']==5);check(act(s,.40,equity=.70,call_pot=230).kind=='call')
h=(Event('blind',6,10),Event('blind',7,20),Event('raise',0,60))
s=state(hero=5,history=h,bets={0:60,6:10,7:20},to_call=60,pot=90)
check(ctx(s)['pot_class']=='raised');check(act(s,.50,equity=.90,call_pot=150).kind=='fold');check(act(s,.08) is None)
check(act(s,.08,equity=.30,call_pot=150).kind=='fold');check(act(s,.08,equity=.60,call_pot=150).kind=='call')
s.history+=(Event('raise',2,180),);s.seats=tuple(Seat(x.seat,x.stack,180 if x.seat==2 else x.bet,x.status) for x in s.seats);s.to_call=180;s.pot=270
check(ctx(s)['raise_count']==2);check(act(s,.08,equity=.8,call_pot=450).kind=='fold');check(act(s,.01,equity=.1,call_pot=450).kind=='fold')
s.board=('Ac','2d','3c');check(act(s,.01,equity=1,call_pot=450) is None)
print({'passed':checks,'failed':0})


# Regression: cheap all-in blind calls cannot become folds simply because raising is unavailable.
s=state(n=2,button=0,hero=0,depth=1,bets={0:10,1:20},stacks={0:1,1:0},statuses={1:'all_in'},to_call=10,pot=30)
s.legal_actions=(LegalAction('fold'),LegalAction('call'))
check(act(s,.99,equity=.60,call_pot=31).kind=='call')
print({'integrated_checks':checks,'failed':0})
