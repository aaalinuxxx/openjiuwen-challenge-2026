def solve(values):
    if not values:return []
    result=[];n=1
    for a,b in zip(values,values[1:]):
        if b>a:n+=1
        else:result.append(n);n=1
    result.append(n)
    return result
