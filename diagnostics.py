"""Exception dependence and uncertainty diagnostics with explicit assumptions."""
import math
import random
from statistics import NormalDist


def wilson_interval(successes, n, level=.95):
    if n < 1 or not 0 <= successes <= n or not 0 < level < 1:
        raise ValueError('Invalid binomial interval inputs')
    z=NormalDist().inv_cdf((1+level)/2)
    phat=successes/n
    denominator=1+z*z/n
    center=(phat+z*z/(2*n))/denominator
    half=z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/denominator
    return [max(0.,center-half),min(1.,center+half)]


def quantile(values, q):
    ordered=sorted(values);index=(len(ordered)-1)*q;lo=int(index)
    return ordered[lo]+(index-lo)*(ordered[min(lo+1,len(ordered)-1)]-ordered[lo])


def block_sample(values, rng, block):
    result=[]
    while len(result)<len(values):
        start=rng.randrange(len(values))
        result.extend(values[(start+i)%len(values)] for i in range(block))
    return result[:len(values)]


def bernoulli_ll(zeros, ones):
    n=zeros+ones
    if not n:return 0.
    p=ones/n
    return (ones*math.log(p) if ones else 0.)+(zeros*math.log1p(-p) if zeros else 0.)


def exception_diagnostics(breaches, kupiec_lr=0.):
    flags=[int(b) for b in breaches];n=len(flags)
    if not n:raise ValueError('No exception observations')
    counts={key:0 for key in ('00','01','10','11')}
    longest=current=0
    for b in flags:
        current=current+1 if b else 0;longest=max(longest,current)
    for a,b in zip(flags,flags[1:]):counts[f'{a}{b}']+=1
    n00,n01,n10,n11=(counts[k] for k in ('00','01','10','11'))
    p01=n01/(n00+n01) if n00+n01 else None
    p11=n11/(n10+n11) if n10+n11 else None
    identifiable=p01 is not None and p11 is not None and 0 < n01+n11 < n-1
    lr=max(0.,2*(bernoulli_ll(n00,n01)+bernoulli_ll(n10,n11)-bernoulli_ll(n00+n10,n01+n11))) if identifiable else None
    rng=random.Random(2026);block=min(10,n)
    means=[sum(block_sample(flags,rng,block))/n for _ in range(600)]
    return {'transitions':counts,'p_exception_after_clear':p01,'p_exception_after_exception':p11,
            'longest_exception_run':longest,'independence_lr':lr,
            'independence_p_value':math.erfc(math.sqrt(lr/2)) if lr is not None else None,
            'conditional_coverage_p_value':math.exp(-(kupiec_lr+lr)/2) if lr is not None else None,
            'wilson_95':wilson_interval(sum(flags),n),
            'block_bootstrap_95':[quantile(means,.025),quantile(means,.975)],
            'block_length':block,'bootstrap_replicates':600,
            'sparse_transitions':min(counts.values())<5,
            'note':'Wilson assumes independent Bernoulli exceptions. Circular-block intervals resample observed sequences; sparse or all-zero exceptions can make them misleading. Independence p-values are asymptotic, not proof of adequacy.'}


def risk_intervals(losses, confidence, tail_function):
    rng=random.Random(912);block=min(10,len(losses));results=[]
    for _ in range(400):results.append(tail_function(block_sample(losses,rng,block),confidence))
    return {'var_95':[quantile([r['var'] for r in results],.025),quantile([r['var'] for r in results],.975)],
            'es_95':[quantile([r['es'] for r in results],.025),quantile([r['es'] for r in results],.975)],
            'block_length':block,'replicates':400,
            'method':'95% percentile circular-block bootstrap; conditional on this 250-observation sample. Not a next-day loss prediction interval.'}
