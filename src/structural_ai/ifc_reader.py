# Imported A01 R06 code; retain the MIT notice in LICENSES/A01-R06-original.txt.
"""Small, strict STEP reader for the supplied A01 IFC4 file.
Not an IFC EXPRESS validator. Rejects unsupported geometry rather than guessing.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
import numpy as np

@dataclass(frozen=True)
class Ref:
    id: int
@dataclass(frozen=True)
class Token:
    value: str
@dataclass(frozen=True)
class Typed:
    name: str
    args: tuple
@dataclass
class Entity:
    id: int
    type: str
    args: tuple

TOK = re.compile(r"\s*(?:(\#[0-9]+)|('(?:[^']|'')*')|([(),])|(\.[A-Z0-9_]+\.)|([*$])|([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)|([A-Z_][A-Z0-9_]*))")
def parse(text):
    ts=[]; pos=0
    while pos < len(text):
        m=TOK.match(text,pos)
        if not m:
            if not text[pos:].strip(): break
            raise ValueError(f'Unsupported STEP token at {text[pos:pos+60]!r}')
        pos=m.end(); a,b,c,d,e,f,g=m.groups()
        if a: ts.append(Ref(int(a[1:])))
        elif b: ts.append(b[1:-1].replace("''", "'"))
        elif c: ts.append(Token(c))
        elif d or e: ts.append(Token(d or e))
        elif f: ts.append(float(f) if any(ch in f for ch in '.Ee') else int(f))
        elif g: ts.append(Typed(g,()))
    n=0
    def val():
        nonlocal n
        t=ts[n]; n+=1
        if t==Token('('):
            vals=[]
            while ts[n]!=Token(')'):
                vals.append(val())
                if ts[n]==Token(','): n+=1
                elif ts[n]!=Token(')'): raise ValueError('Missing comma')
            n+=1; return tuple(vals)
        if isinstance(t,Typed):
            return Typed(t.name,val())
        return t
    result=val()
    if n !=len(ts): raise ValueError('Trailing tokens')
    return result

def encode(x):
    if isinstance(x,Ref): return f'#{x.id}'
    if isinstance(x,Token): return x.value
    if isinstance(x,Typed): return x.name+encode(x.args)
    if isinstance(x,str): return "'"+x.replace("'","''")+"'"
    if isinstance(x,tuple) or isinstance(x,list): return '('+','.join(encode(v) for v in x)+')'
    if isinstance(x,int): return str(x)
    if isinstance(x,float):
        if not np.isfinite(x): raise ValueError('Nonfinite IFC number')
        s=f'{x:.12g}'; return s if '.' in s or 'e' in s else s+'.'
    raise TypeError(type(x))

NULL=Token('$')
class Model:
    def __init__(self,path):
        self.path=Path(path); self.text=self.path.read_text(encoding='utf8')
        self.entities={}
        for match in re.finditer(r'^#(\d+)\s*=\s*(\w+)\((.*)\);\s*$',self.text,re.M):
            tag,typ,arg=match.groups(); i=int(tag)
            if i in self.entities: raise ValueError('Duplicate entity id')
            self.entities[i]=Entity(i,typ,parse('('+arg+')'))
        if not self.entities: raise ValueError('No STEP entities parsed')
        self.validate_refs()
    def __getitem__(self,x): return self.entities[x.id if isinstance(x,Ref) else x]
    def by_type(self,name): return [e for e in self.entities.values() if e.type==name.upper()]
    def validate_refs(self):
        def walk(a):
            if isinstance(a,Ref):
                if a.id not in self.entities: raise ValueError(f'Dangling {a}')
            elif isinstance(a,Typed): walk(a.args)
            elif isinstance(a,tuple):
                for v in a: walk(v)
        for e in self.entities.values(): walk(e.args)
    def axis(self,r):
        if r==NULL: return np.eye(4)
        e=self[r]; p=np.array(self[e.args[0]].args[0],float); m=np.eye(4)
        if e.type=='IFCAXIS2PLACEMENT3D':
            z=np.array([0,0,1] if e.args[1]==NULL else self[e.args[1]].args[0],float); z/=np.linalg.norm(z)
            x=np.array([1,0,0] if e.args[2]==NULL else self[e.args[2]].args[0],float)
            x=x-z*np.dot(z,x); x/=np.linalg.norm(x); y=np.cross(z,x)
            m[:3,:3]=np.column_stack([x,y,z]); m[:3,3]=p
        elif e.type=='IFCAXIS2PLACEMENT2D':
            x=np.array([1,0] if e.args[1]==NULL else self[e.args[1]].args[0],float); x/=np.linalg.norm(x)
            m[:2,:2]=np.column_stack([x,[-x[1],x[0]]]); m[:2,3]=p
        else: raise ValueError(e.type)
        return m
    def placement(self,r):
        if r==NULL: return np.eye(4)
        e=self[r]
        if e.type!='IFCLOCALPLACEMENT': raise ValueError(e.type)
        return self.placement(e.args[0])@self.axis(e.args[1])
    def solids(self,e):
        if e.args[6]==NULL: return []
        reps=self[e.args[6]].args[2]; out=[]
        for r in reps:
            rep=self[r]
            if rep.args[1]=='Body': out.extend(self[a] for a in rep.args[3])
        return out
    def solid_geometry(self,e):
        solids=self.solids(e)
        if len(solids)!=1 or solids[0].type!='IFCEXTRUDEDAREASOLID': raise ValueError(f'Unsupported shape {e.type}/{e.id}')
        so=solids[0]; pr=self[so.args[0]]
        if pr.type=='IFCRECTANGLEPROFILEDEF':
            w,d=pr.args[3:5]; pts=np.array([[-w/2,-d/2],[w/2,-d/2],[w/2,d/2],[-w/2,d/2]],float)
            pmat=self.axis(pr.args[2])
        elif pr.type=='IFCARBITRARYCLOSEDPROFILEDEF':
            curve=self[pr.args[2]]
            if curve.type!='IFCPOLYLINE': raise ValueError(curve.type)
            pts=np.array([self[p].args[0] for p in curve.args[0]],float)[:,:2]; pmat=np.eye(4)
            if np.allclose(pts[0],pts[-1]): pts=pts[:-1]
        else: raise ValueError(pr.type)
        v=np.c_[pts,np.zeros(len(pts)),np.ones(len(pts))]@pmat.T
        ex=np.array(self[so.args[2]].args[0],float); ex/=np.linalg.norm(ex)
        v2=v.copy(); v2[:,:3]+=ex*so.args[3]
        matrix=self.placement(e.args[5])@self.axis(so.args[1])
        vertices=(np.vstack([v,v2])@matrix.T)[:,:3]
        area=abs(np.dot(pts[:,0],np.roll(pts[:,1],-1))-np.dot(pts[:,1],np.roll(pts[:,0],-1)))/2
        return {'min':vertices.min(0),'max':vertices.max(0),'volume':area*float(so.args[3]),'vertices':vertices,'profile':pts,'matrix':matrix,'solid':so}
    def psets(self,e):
        props={}
        for rel in self.by_type('IFCRELDEFINESBYPROPERTIES'):
            if Ref(e.id) in rel.args[4]:
                pset=self[rel.args[5]]; d={}
                for p in pset.args[4]:
                    pv=self[p]; vv=pv.args[2]
                    d[pv.args[0]]=vv.args[0] if isinstance(vv,Typed) else vv
                props[pset.args[2]]=d
        return props
    def new(self,type,*args):
        i=max(self.entities)+1; self.entities[i]=Entity(i,type.upper(),tuple(args)); return Ref(i)
    def write(self,path,header=None):
        h=self.text.split('DATA;')[0]+'DATA;\n' if header is None else header
        Path(path).write_text(h+'\n'.join(f'#{i}={e.type}{encode(e.args)};' for i,e in sorted(self.entities.items()))+'\nENDSEC;\nEND-ISO-10303-21;\n',encoding='utf8')

