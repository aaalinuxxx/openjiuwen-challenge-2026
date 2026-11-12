def run_lengths(values):
    out=[]
    for x in values:
        if out and out[-1][0]==x:out[-1]=(x,out[-1][1]+1)
        else:out.append((x,1))
    return out
