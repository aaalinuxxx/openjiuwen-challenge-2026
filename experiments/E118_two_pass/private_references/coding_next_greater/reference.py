def solve(values):
    out=[]
    for i,x in enumerate(values):
        out.append(next((y for y in values[i+1:] if y>x),None))
    return out
