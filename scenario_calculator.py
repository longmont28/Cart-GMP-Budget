import math

def binomial_tail(n,k,p):
    return sum(math.comb(n,i)*p**i*(1-p)**(n-i) for i in range(k,n+1))

def required_screened(target=12,screening=.7,manufacturing=.7,assurance=.9):
    p=screening*manufacturing
    if not 0<p<=1: raise ValueError('probabilities must be positive and <=1')
    n=target
    while binomial_tail(n,target,p)<assurance:n+=1
    return {'screened':n,'expected_manufacturing_starts':n*screening,'expected_infused':n*p,'probability_at_least_target':binomial_tail(n,target,p)}

if __name__=='__main__':
    for r in (.5,.7,.9): print(f'{r:.0%}',required_screened(screening=r,manufacturing=r))
