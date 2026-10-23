"""Independent numerical example of paid cash, inventory and collateral."""
from market_making_lab.core import Config,execute,fair_values
c=Config();cash,q,delta=execute(10.,0,1,.4,c)
assert abs(float(cash)-9.599)<1e-12 and q==1
after,q,delta=execute(cash,q,-1,.45,c)
assert abs(float(after)-10.048)<1e-12 and q==0
blocked,q,delta=execute(.1,0,-1,.6,c)
assert blocked==.1 and q==0 and delta==0
assert abs(fair_values(1)[1,5]-.48)<1e-12
print({'buy_cash':float(cash),'round_trip_cash':float(after),'short_collateral_rejection':True})
