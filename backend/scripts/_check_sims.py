import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, ".")
from core.database import get_session_maker
from core.models.simulator import Simulator

db = get_session_maker()()
sims = db.query(Simulator).all()
for s in sims:
    pt = s.prompt_template or ""
    sp = s.secondary_prompt or ""
    gt = s.grader_template or ""
    print(f"  {s.name} | type={s.interaction_type} | preset={s.is_preset} | prompt={len(pt)} | secondary={len(sp)} | grader={len(gt)}")
db.close()

