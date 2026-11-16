import re
def tokenize(s):
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', s)
def parse(s):
    toks=tokenize(s); pos=0
    def rd():
        nonlocal pos
        t=toks[pos]; pos+=1
        if t=='(':
            l=[]
            while toks[pos]!=')': l.append(rd())
            pos+=1; return l
        return t
    return rd()
def dump(x, ind=0):
    if isinstance(x,list):
        if all(not isinstance(e,list) for e in x):
            return '('+' '.join(x)+')'
        out='('+' '.join(e for e in x if not isinstance(e,list))
        # keep order
        parts=[]
        head=[]
        for e in x:
            parts.append(dump(e,ind+1) if isinstance(e,list) else e)
        return '('+' '.join(parts)+')'
    return x
def find(x,key):
    return [e for e in x if isinstance(e,list) and e and e[0]==key]
