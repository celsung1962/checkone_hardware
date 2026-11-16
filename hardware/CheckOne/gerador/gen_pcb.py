import sys, os
sys.path.insert(0,'.')
import pcbnew, design
FP='/usr/share/kicad/footprints'
B=pcbnew.BOARD()
mm=pcbnew.FromMM
CX,CY=150.0,100.0
def M(x,z): return (CX+x, CY-z)
def load(fpid):
    lib,name=fpid.split(':')
    path=f'CheckOne/CheckOne.pretty' if lib=='CheckOne' else f'{FP}/{lib}.pretty'
    f=pcbnew.FootprintLoad(path,name)
    if f is None: raise RuntimeError(fpid)
    return f
nets={}
def net(n):
    if n not in nets:
        ni=pcbnew.NETINFO_ITEM(B,n); B.Add(ni); nets[n]=ni
    return nets[n]
# ---------- posições fixas (coordenadas do modelo 3D: x ao longo de 145, z ao longo de 90) ----------
termX=[-38.04,-16.12,5.80,27.72]
fixed={}
for k,x in enumerate(termX):
    fixed[f'J1{k+1}']=(CX+x-1.5*5.08, CY-43.5-1+10.9, 0)      # CH1-4 na borda superior, encaixe para fora
    fixed[f'J1{k+5}']=(CX+x+1.5*5.08, CY+43.5+1-10.9, 180)    # CH5-8 na borda inferior
fixed['J1']=(CX+45.4, CY-43.5-0.5+13.8, 180)                 # DC-005 na borda superior, boca para fora
fixed['J2']=(*M(41.8,-40.1),0)                          # NTC1 na janela frontal
fixed['J3']=(*M(-54-1.25,-28),0)                             # NTC2 interno
fixed['J4']=(*M(28.5,-5),0); fixed['J5']=(*M(-31,-17),0); fixed['J6']=(*M(-17,-17),0)
fixed['J7']=(*M(-56,24+3.81),0)
fixed['BT1']=(*M(-48-2.3,6),0)
for i,(lx,lz) in enumerate([(49.3,-42.4),(49.3,-40.2),(49.3,-38.0),(49.3,-35.8)]): fixed[f'LED{i+1}']=(*M(lx,lz),0)
fixed['Q1']=(*M(56.5,15),90); fixed['U1']=(*M(55,-5),0); fixed['L2']=(*M(54.5,-17),90); fixed['C12']=(*M(38,-15.5),0)
fixed['C2']=(*M(0,15),0); fixed['C5']=(*M(14.5,15),0); fixed['L1']=(*M(9,2),0); fixed['C7']=(*M(23,3.6),0)
fixed['C10']=(*M(44,-2),0); fixed['C14']=(*M(29,15),0)
for i,(x,z) in enumerate([(-57.5,40),(57.5,40),(-57.5,-40),(57.5,-40)]): fixed[f'H{i+1}']=(*M(x,z),0)
for i,(x,z) in enumerate([(-43.5,24.5),(43.5,24.5),(-43.5,-24.5),(43.5,-24.5)]): fixed[f'H{i+5}']=(*M(x,z),0)
for i in range(8): fixed[f'TP{i+1}']=(*M(-24+i*8,-2),0)
# âncoras dos grupos (os componentes de cada grupo são distribuídos ao redor)
anchor={'in':(53,28),'ss':(48,10),'flt':(26,4),'buck':(46,-9),'disp5':(38,-11),'ina':(38,8),'ldo':(24,-21),'led':(44,-30),'i2c':(-20,-23),
        'ads1':(-6,15),'ads2':(-6,-12),'ads3':(36,-25),'ntc1':(30,-31),'ntc2':(-47,-22),'rtc':(-53,-12),'jpwr':(33,-5),'ji2c':(-23,-17),'jext':(-56,24),'bat':(-48,6),'mh':(0,0),'tp':(0,0),'dc':(44.7,38)}
for n in range(1,9):
    x=termX[(n-1)%4]; anchor[f'ch{n}']=(x, 22 if n<=4 else -22)
import math
truefixed=set(fixed)
fps={}; boxes=[]
X0,Y0,X1,Y1=CX-61+0.6,CY-43.5+0.6,CX+61-0.6,CY+43.5-0.6
def bbox(f,margin=0.35):
    bb=f.GetBoundingBox(False,False)
    return (pcbnew.ToMM(bb.GetLeft())-margin,pcbnew.ToMM(bb.GetTop())-margin,pcbnew.ToMM(bb.GetRight())+margin,pcbnew.ToMM(bb.GetBottom())+margin)
def hit(bx):
    if bx[0]<X0 or bx[1]<Y0 or bx[2]>X1 or bx[3]>Y1: return True
    for o in boxes:
        if bx[0]<o[2] and bx[2]>o[0] and bx[1]<o[3] and bx[3]>o[1]: return True
    return False
def make(p):
    f=load(p['fp']); f.SetReference(p['ref']); f.SetValue(p['val'])
    for pad in f.Pads():
        num=pad.GetNumber()
        if num in p['pins'] and not p['pins'][num].startswith('NC_'): pad.SetNet(net(p['pins'][num]))
    if p['lcsc']: f.SetProperty('LCSC',p['lcsc'])
    if p['dnp'] or not p['lcsc']: f.SetAttributes(f.GetAttributes()|pcbnew.FP_EXCLUDE_FROM_BOM|pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    return f
# reserva da serigrafia (rótulos dos bornes e dos conectores) antes da distribuição automática
for k,x in enumerate(termX):
    yt=CY-43.5-1+10.9+2.6; boxes.append((CX+x-11,yt-0.7,CX+x+11,yt+3.4))
    yb=CY+43.5+1-10.9-2.6; boxes.append((CX+x-11,yb-3.4,CX+x+11,yb+0.7))
for (x,z,w) in [(28.5,-9.5,16),(-31,-21.5,17),(-17,-23.5,19),(-22,2,26)]:
    X,Y=M(x,z); boxes.append((X-w/2,Y-0.8,X+w/2,Y+0.8))
order=[p for p in design.parts if p['ref'] in truefixed]+[p for p in design.parts if p['ref'] not in truefixed]
for p in order:
    f=make(p); B.Add(f); fps[p['ref']]=f
    if p['ref'] in truefixed:
        x,y,rot=fixed[p['ref']]
        f.SetPosition(pcbnew.VECTOR2I(mm(x),mm(y))); f.SetOrientationDegrees(rot)
        if p['ref'].startswith('TP'): f.Flip(f.GetPosition(),False); continue
        boxes.append(bbox(f,0.2)); continue
    ax,az=anchor[p['grp']]; cx,cy=M(ax,az)
    done=False
    for r in [i*0.5 for i in range(0,140)]:
        n=max(1,int(2*math.pi*r/0.8)) if r>0 else 1
        for k in range(n):
            t=2*math.pi*k/n
            for rot in (0,90):
                x=cx+r*math.cos(t); y=cy+r*math.sin(t)
                f.SetPosition(pcbnew.VECTOR2I(mm(round(x,2)),mm(round(y,2)))); f.SetOrientationDegrees(rot)
                bx=bbox(f)
                if not hit(bx): boxes.append(bx); done=True; break
            if done: break
        if done: break
    if not done: print('sem lugar:',p['ref'])
# ---------- contorno ----------
x0,y0,x1,y1=CX-61,CY-43.5,CX+61,CY+43.5
for (a,b) in [((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))]:
    s=pcbnew.PCB_SHAPE(B); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetStart(pcbnew.VECTOR2I(mm(a[0]),mm(a[1]))); s.SetEnd(pcbnew.VECTOR2I(mm(b[0]),mm(b[1])))
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.1)); B.Add(s)
# ---------- serigrafia ----------
def silk(txt,x,y,size=1.0,rot=0,layer=pcbnew.F_SilkS,bold=False):
    t=pcbnew.PCB_TEXT(B); t.SetText(txt); t.SetPosition(pcbnew.VECTOR2I(mm(x),mm(y))); t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size),mm(size))); t.SetTextThickness(mm(size*(0.2 if bold else 0.15))); t.SetTextAngleDegrees(rot)
    if layer==pcbnew.B_SilkS: t.SetMirrored(True)
    B.Add(t)
names=['+24','GND','Iin','Iout']
for k,x in enumerate(termX):
    yt=CY-43.5-1+10.9+2.6
    silk(f'CH{k+1}',CX+x,yt+2.2,1.5,bold=True)
    for i in range(4): silk(names[i],CX+x-1.5*5.08+i*5.08,yt,0.8)
    yb=CY+43.5+1-10.9-2.6
    silk(f'CH{k+5}',CX+x,yb-2.2,1.5,bold=True)
    for i in range(4): silk(names[i],CX+x+1.5*5.08-i*5.08,yb,0.8)
silk('24V DC  (+) centro',CX+45.4,CY-43.5+16.5,0.9,bold=True)
silk('NTC1',*M(44.5,-34.6),1.0,bold=True); silk('NTC2',*M(-54,-23.4),1.0,bold=True)
for txt,(lx,lz) in zip(['24V','5V','3V3','3V3D'],[(48.6,-42.4),(48.6,-40.2),(48.6,-38.0),(48.6,-35.8)]): silk(txt,CX+lx-2.9,CY-lz,0.7)
silk('DISPLAY 5V: 5V TX RX GND',*M(28.5,-9.5),0.7); silk('I2C CYD: GND SCL SDA 3V3',*M(-31,-21.5),0.7); silk('I2C JC3248: GND 3V3 SDA SCL',*M(-17,-23.5),0.7)
silk('DISPLAY EXT: 5V GND SDA SCL',*M(-51.5,24),0.7,rot=90); silk('CR2032 +',*M(-48,19),1.0,bold=True)
silk('CheckOne · AQTech  rev 1.0',*M(-22,2),1.2,bold=True)
for i,n in enumerate(['24V','5V','3V3','3V3A','SDA','SCL','GND','GND']): silk(n,*M(-24+i*8,-4.5),0.8,layer=pcbnew.B_SilkS)
# ---------- regras (JLCPCB, 2 camadas) ----------
ds=B.GetDesignSettings()
ds.m_TrackMinWidth=mm(0.2); ds.m_MinClearance=mm(0.2); ds.m_ViasMinSize=mm(0.6); ds.m_MinThroughDrill=mm(0.3)
ds.SetCopperLayerCount(2)
pcbnew.SaveBoard('CheckOne/CheckOne.kicad_pcb',B)
# ---------- verificação de sobreposição (corpo dos componentes) ----------
items=[]
for r,f in fps.items():
    if r.startswith('TP'): continue
    bb=f.GetBoundingBox(False,False); bb.Inflate(-pcbnew.FromMM(0.15)); items.append((r,bb))
ov=[]
for i in range(len(items)):
    for j in range(i+1,len(items)):
        if items[i][1].Intersects(items[j][1]): ov.append((items[i][0],items[j][0]))
print('componentes:',len(fps),'| redes:',len(nets),'| pares sobrepostos:',len(ov))
print(ov[:40])
