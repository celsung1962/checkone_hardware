import sys, uuid, copy, math
sys.path.insert(0,'.')
from sexp import parse, find
import design
U=lambda: str(uuid.uuid4())
LIBDIR='/usr/share/kicad/symbols'
cache={}
def lib(name):
    if name not in cache:
        path='CheckOne/CheckOne.kicad_sym' if name=='CheckOne' else f'{LIBDIR}/{name}.kicad_sym'
        cache[name]=parse(open(path).read())
    return cache[name]
def getsym(libname,name):
    for s in find(lib(libname),'symbol'):
        if s[1].strip('"')==name: return s
    raise KeyError(name)
def flat(lib_id):
    ln,sn=lib_id.split(':')
    s=copy.deepcopy(getsym(ln,sn))
    ext=find(s,'extends')
    if ext:
        parent=copy.deepcopy(getsym(ln,ext[0][1].strip('"')))
        pname=parent[1].strip('"')
        props={p[1]:p for p in find(s,'property')}
        new=[parent[0],f'"{lib_id}"']
        for e in parent[2:]:
            if isinstance(e,list) and e[0]=='property' and e[1] in props: new.append(props[e[1]])
            elif isinstance(e,list) and e[0]=='symbol':
                e=copy.deepcopy(e); e[1]='"'+e[1].strip('"').replace(pname,sn,1)+'"'; new.append(e)
            else: new.append(e)
        return new
    s[1]=f'"{lib_id}"'
    return s
def pins_of(sym):
    out=[]
    def walk(x):
        for e in x:
            if isinstance(e,list):
                if e[0]=='pin':
                    num=find(e,'number')[0][1].strip('"'); at=find(e,'at')[0]
                    ln=find(e,'length'); L=float(ln[0][1]) if ln else 2.54
                    out.append((num,float(at[1]),float(at[2]),float(at[3]) if len(at)>3 else 0.0,L))
                else: walk(e)
    walk(sym); return out
def dump(x):
    if isinstance(x,list): return '('+' '.join(dump(e) for e in x)+')'
    return x
G=1.27
snap=lambda v: round(v/G)*G
def q(s): return '"'+s.replace('"','\\"')+'"'
ROOT=U()
sheets=[('alimentacao','Alimentação e proteção'),('canais','Canais CH1–CH8'),('adcs','ADCs e NTC'),('display_rtc','Display, RTC e fixação')]
sheet_uuid={k:U() for k,_ in sheets}
def gen_sheet(key,title,page):
    parts=[p for p in design.parts if p['sheet']==key]
    libsyms={}
    for p in parts: libsyms[p['sym']]=flat(p['sym'])
    items=[]
    # grupos em linhas
    groups=[]; 
    for p in parts:
        if not groups or groups[-1][0]!=p['grp']: groups.append([p['grp'],[]])
        groups[-1][1].append(p)
    x0,y0=25.4,30.48; x=x0; y=y0; rowh=0; maxw=380
    for gname,gparts in groups:
        # largura do grupo
        boxes=[]
        for p in gparts:
            ps=pins_of(libsyms[p['sym']])
            xs=[a[1] for a in ps]+[0]; ys=[a[2] for a in ps]+[0]
            w=(max(xs)-min(xs))+30; h=(max(ys)-min(ys))+15
            boxes.append((p,ps,min(xs),max(ys),w,h))
        gw=sum(b[4] for b in boxes)+10
        if x+gw>maxw: x=x0; y+=rowh+12; rowh=0
        items.append(f'(text {q("Grupo: "+gname)} (at {snap(x)} {snap(y-6)} 0) (effects (font (size 1.5 1.5) bold) (justify left)) (uuid {U()}))')
        for p,ps,minx,maxy,w,h in boxes:
            sx=snap(x-minx+12); sy=snap(y+maxy+4)
            pinlines=' '.join(f'(pin {q(n)} (uuid {U()}))' for n,*_ in ps)
            right=max([a[1] for a in ps]+[0]); top=max([a[2] for a in ps]+[0]); bottom=min([a[2] for a in ps]+[0])
            fx=snap(sx+right+2.54) if right<=2.6 else snap(sx); 
            if right<=2.6:
                pos={'Reference':(fx,snap(sy-1.27),'left'),'Value':(fx,snap(sy+1.27),'left')}
            else:
                pos={'Reference':(snap(sx),snap(sy-top-2.54),'left'),'Value':(snap(sx),snap(sy-bottom+2.54),'left')}
            fields=[('Reference',p['ref']),('Value',p['val']),('Footprint',p['fp']),('Datasheet','~'),('LCSC',p['lcsc'])]
            props=''
            for k,v in fields:
                px_,py_,j=pos.get(k,(snap(sx),snap(sy),'left'))
                hide=' hide' if k in ('Footprint','Datasheet','LCSC') else ''
                props+=f'(property {q(k)} {q(v)} (at {px_} {py_} 0) (effects (font (size 1.27 1.27)) (justify {j}){hide}))'
            pinlines=' '.join(f'(pin {q(n)} (uuid {U()}))' for n,*_ in ps)
            items.append(f'(symbol (lib_id {q(p["sym"])}) (at {sx} {sy} 0) (unit 1) (in_bom yes) (on_board yes) (dnp {"yes" if p["dnp"] else "no"}) (uuid {U()}) {props} {pinlines} (instances (project "CheckOne" (path "/{ROOT}/{sheet_uuid[key]}" (reference {q(p["ref"])}) (unit 1)))))')
            stubs={}
            for n,px,py,ang,L in ps:
                if n not in p['pins']:
                    if p['sym'].startswith('Mechanical'): continue
                    net=None
                else: net=p['pins'][n]
                ex=snap(sx+px); ey=snap(sy-py)
                out=math.radians(ang+180); dx=round(math.cos(out)); dy=-round(math.sin(out))
                lx=snap(ex+dx*2.54); ly=snap(ey+dy*2.54)
                if net is None or net.startswith('NC_'):
                    items.append(f'(no_connect (at {ex} {ey}) (uuid {U()}))'); continue
                items.append(f'(wire (pts (xy {ex} {ey}) (xy {lx} {ly})) (stroke (width 0) (type default)) (uuid {U()}))')
                stubs.setdefault((net,dx,dy),[]).append((lx,ly))
            allpts={pt:nk for nk,pl in stubs.items() for pt in pl}
            for (net,dx,dy),pts in stubs.items():
                pts=sorted(pts)
                chains=[[pts[0]]]
                for b in pts[1:]:
                    a=chains[-1][-1]
                    between=[pt for pt,nk in allpts.items() if nk[0]!=net and min(a[0],b[0])<=pt[0]<=max(a[0],b[0]) and min(a[1],b[1])<=pt[1]<=max(a[1],b[1]) and (a[0]==b[0] or a[1]==b[1])]
                    if (a[0]==b[0] or a[1]==b[1]) and not between: chains[-1].append(b)
                    else: chains.append([b])
                la={(-1,0):180,(1,0):0,(0,-1):90,(0,1):270}[(dx,dy)]
                just='right' if la==180 else 'left'
                for ch in chains:
                    for a,b in zip(ch,ch[1:]):
                        items.append(f'(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default)) (uuid {U()}))')
                    for a in ch[1:-1]:
                        items.append(f'(junction (at {a[0]} {a[1]}) (diameter 0) (color 0 0 0 0) (uuid {U()}))')
                    lx,ly=ch[0]
                    items.append(f'(global_label {q(net)} (shape passive) (at {lx} {ly} {la}) (fields_autoplaced) (effects (font (size 1.27 1.27)) (justify {just})) (uuid {U()}) (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {lx} {ly} 0) (effects (font (size 1.27 1.27)) hide)))')
            x+=w
            rowh=max(rowh,h)
        x+=10
    libtxt='(lib_symbols '+' '.join(dump(s) for s in libsyms.values())+')'
    body=f'(kicad_sch (version 20230121) (generator eeschema) (uuid {sheet_uuid[key]}) (paper "A2") (title_block (title {q("CheckOne — "+title)}) (company "AQTech Power Prognostics") (rev "1.0")) {libtxt} '+' '.join(items)+')'
    open(f'CheckOne/{key}.kicad_sch','w').write(body)
# raiz
items=[]
for i,(k,t) in enumerate(sheets):
    x=25.4+i*70; y=40
    items.append(f'(sheet (at {x} {y}) (size 55 25) (fields_autoplaced) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid {sheet_uuid[k]}) (property "Sheetname" {q(t)} (at {x} {y-0.7} 0) (effects (font (size 1.27 1.27)) (justify left bottom))) (property "Sheetfile" "{k}.kicad_sch" (at {x} {y+25.6} 0) (effects (font (size 1.27 1.27)) (justify left top))) (instances (project "CheckOne" (path "/{ROOT}" (page "{i+2}")))))')
items.append(f'(text "CheckOne v1 — jiga de produção (AQTech). Esquemático gerado a partir da netlist única; redes ligadas por rótulos globais." (at 25.4 25 0) (effects (font (size 2 2)) (justify left)) (uuid {U()}))')
open('CheckOne/CheckOne.kicad_sch','w').write(f'(kicad_sch (version 20230121) (generator eeschema) (uuid {ROOT}) (paper "A4") (title_block (title "CheckOne — Jiga de produção") (company "AQTech Power Prognostics") (rev "1.0")) (lib_symbols) '+' '.join(items)+' (sheet_instances (path "/" (page "1"))))')
for i,(k,t) in enumerate(sheets): gen_sheet(k,t,i+2)
print('ok')
