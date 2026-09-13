# Imported A01 R06 code; retain the MIT notice in LICENSES/A01-R06-original.txt.
"""Create R06 IFC and a connected 3D analytical model from the A01 R05 source.
This extractor intentionally supports only the supplied A01 geometry subset.
It is not a general BIM-to-FEM converter. Re-run after editing analysis_input.yaml.
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json, math, uuid, hashlib, argparse
from datetime import datetime, timezone
import numpy as np
import yaml
from shapely.geometry import box, Point
from shapely.ops import unary_union
from .ifc_reader import Model,Ref,Token,Typed,NULL

_guid_index=0
def guid():
    global _guid_index
    _guid_index+=1
    alpha='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$'; n=uuid.uuid5(uuid.NAMESPACE_URL,'A01-R06-generated-entity-'+str(_guid_index)).int; chars=[]
    for _ in range(22): chars.append(alpha[n&63]); n >>=6
    return ''.join(reversed(chars))

def extend_ifc(source,base_z,out,revision='R06'):
    global _guid_index
    _guid_index=0
    m=Model(source); owner=Ref(5); zdir=Ref(6); xdir=Ref(7)
    def pl(rel,x,y,z):
        p=m.new('IFCCARTESIANPOINT',(float(x),float(y),float(z)))
        a=m.new('IFCAXIS2PLACEMENT3D',p,zdir,xdir)
        return m.new('IFCLOCALPLACEMENT',rel,a)
    basepl=pl(Ref(24),0,0,base_z)
    st=m.new('IFCBUILDINGSTOREY',guid(),owner,'BASE_REF',
        'Analysis reference elevation, NOT a basement floor or a designed foundation.',NULL,basepl,NULL,NULL,Token('.ELEMENT.'),float(base_z))
    agg=m[44]; a=list(agg.args); a[5]=a[5]+(st,); agg.args=tuple(a)
    added=[]; newnames={}
    lowest={}
    for typ in ['IFCCOLUMN','IFCWALL']:
        for e in m.by_type(typ):
            if 'A01_NonstructuralPanel' in m.psets(e): continue
            prefix=e.args[2].rsplit('-',1)[0]
            lowest[prefix]=min(lowest.get(prefix,0.),float(m.solid_geometry(e)['min'][2]))
    for typ in ['IFCCOLUMN','IFCWALL']:
        for e in list(m.by_type(typ)):
            if 'A01_NonstructuralPanel' in m.psets(e): continue
            g=m.solid_geometry(e)
            bottom=lowest[e.args[2].rsplit('-',1)[0]]
            if abs(g['min'][2]-bottom)>1e-6: continue
            if bottom<=base_z: raise ValueError('Trial base must be below the lowest source stem')
            name=e.args[2].rsplit('-',1)[0]+'-BASE'
            lo,hi=g['min'],g['max']; w,d=hi[0]-lo[0],hi[1]-lo[1]
            ep=pl(basepl,(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,0)
            pr=m.new('IFCRECTANGLEPROFILEDEF',Token('.AREA.'),NULL,NULL,float(w),float(d))
            o=m.new('IFCCARTESIANPOINT',(0.,0.,0.)); ap=m.new('IFCAXIS2PLACEMENT3D',o,zdir,xdir)
            sol=m.new('IFCEXTRUDEDAREASOLID',pr,ap,zdir,float(bottom-base_z))
            sr=m.new('IFCSHAPEREPRESENTATION',Ref(11),'Body','SweptSolid',(sol,))
            ps=m.new('IFCPRODUCTDEFINITIONSHAPE',NULL,NULL,(sr,))
            p=m.new(typ,guid(),owner,name,'Below-grade structural segment to TRIAL fixed base; NOT a designed footing.',NULL,ep,ps,name,Token('.COLUMN.' if typ=='IFCCOLUMN' else '.SHEAR.'))
            added.append(p); newnames[name]=p.id
            pv=m.new('IFCPROPERTYSINGLEVALUE','TrialBaseElevation_m',NULL,Typed('IFCLENGTHMEASURE',(float(base_z),)),NULL)
            pu=m.new('IFCPROPERTYSINGLEVALUE','AnalysisRole',NULL,Typed('IFCTEXT',('LOAD_BEARING_TO_TRIAL_BASE; no ground restraint at 0.0m',)),NULL)
            pset=m.new('IFCPROPERTYSET',guid(),owner,'A01_R06_BelowGrade',NULL,(pv,pu))
            m.new('IFCRELDEFINESBYPROPERTIES',guid(),owner,NULL,NULL,(p,),pset)
            m.new('IFCRELCONNECTSELEMENTS',guid(),owner,'Ground-level continuity',
                'Matched face / analytical nodes; reinforcement anchorage not designed.',NULL,p,Ref(e.id))
    m.new('IFCRELCONTAINEDINSPATIALSTRUCTURE',guid(),owner,NULL,NULL,tuple(added),st)
    m.new('IFCRELASSOCIATESMATERIAL',guid(),owner,'Added RC below-grade segments',NULL,tuple(added),Ref(45))
    proj=m[17]; a=list(proj.args); a[2]=f'A01 Structural {revision} - analysis trial'; a[3]='Companion analytical_model.json; execute with the OpenSees adapter. Trial fixed base. NOT FOR CONSTRUCTION.'; proj.args=tuple(a)
    # Preserve the complete R05 design log but label it historical, not current status.
    m[3145].args=tuple('A01_R05_HistoricalDesignStatus' if i==2 else a for i,a in enumerate(m[3145].args))
    vals=[]
    for k,v in {'Revision':revision,'PhysicalSource':Path(source).name,
                'SourceSHA256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                'AnalyticalModel':'analytical_model.json','AnalysisScope':'FIRST_ORDER_LINEAR_ELASTIC; gross-section baseline',
                'BaseCondition':f'All translations and rotations fixed at {base_z:.3f} m; assumption only',
                'GroundFloor':'S-1F is excluded from frame stiffness; no fixity at grade',
                'StructuralDesign':'NOT COMPLETED; no member capacity/reinforcement checks',
                'OpenSeesValidation':'NOT RUN in authoring environment',
                'ConstructionUse':'PROHIBITED; research analysis baseline'}.items():
        vals.append(m.new('IFCPROPERTYSINGLEVALUE',k,NULL,Typed('IFCTEXT',(v,)),NULL))
    ps=m.new('IFCPROPERTYSET',guid(),owner,'A01_R06_AnalysisStatus',NULL,tuple(vals))
    m.new('IFCRELDEFINESBYPROPERTIES',guid(),owner,NULL,NULL,(Ref(25),),ps)
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    header=f"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('A01 {revision} physical model and analysis reference; NOT FOR CONSTRUCTION'),'2;1');\nFILE_NAME('{out.name}','{now}',('A01 research prototype'),('Not a licensed design office'),'A01 subset generator','A01 {revision}','');\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
    m.validate_refs(); m.write(out,header)
    return Model(out)

def subdivide(values,h):
    a=sorted(set(round(float(v),8) for v in values)); out=[a[0]]
    for u,v in zip(a[:-1],a[1:]):
        n=max(1,int(math.ceil((v-u)/h-1e-8)))
        out.extend(round(u+(v-u)*i/n,8) for i in range(1,n+1))
    return out

def create(source,config,outdir,mesh_size=None,architect_scheme=None,equipment_basis=None):
    cfg=yaml.safe_load(Path(config).read_text()); bz=float(cfg['base']['elevation_m'])
    if architect_scheme is None:
        raise ValueError('H02 requires the authoritative architectural scheme for stair finishes')
    scheme=yaml.safe_load(Path(architect_scheme).read_text())
    revised=cfg.get('revision') in ('H03-B','H03-C')
    joint_revision=cfg.get('revision')=='H03-C'
    if revised and equipment_basis is None:
        raise ValueError('H03-B requires the recorded synthetic equipment basis')
    equipment=yaml.safe_load(Path(equipment_basis).read_text()) if revised else None
    if bz>=0: raise ValueError('This baseline requires a negative base elevation')
    h=float(cfg['mesh']['target_size_m'] if mesh_size is None else mesh_size)
    if not math.isfinite(h) or h<=0: raise ValueError('Finite positive mesh size required')
    outdir=Path(outdir); outdir.mkdir(parents=True,exist_ok=True)
    physical_name=f"A01_Structural_{cfg['revision']}_Candidate.ifc" if revised else 'A01_Structural_R06_AnalysisReady.ifc'
    m=extend_ifc(source,bz,outdir/physical_name,cfg['revision'] if revised else 'R06')
    products={e.args[2]:e for typ in ['IFCCOLUMN','IFCBEAM','IFCWALL','IFCSLAB','IFCSTAIRFLIGHT','IFCOPENINGELEMENT'] for e in m.by_type(typ)}
    geom={k:m.solid_geometry(v) for k,v in products.items()}
    voids=defaultdict(list)
    for r in m.by_type('IFCRELVOIDSELEMENT'): voids[m[r.args[4]].args[2]].append(m[r.args[5]].args[2])
    levels={'BASE_REF':bz,'1F':0.,'2F':4.,'3F':7.6,'RF':11.2}
    # Joined midplanes: this is an explicit analytical idealization of the R05
    # wall corners, not a move of the physical walls or the building grid.
    wall_lines={
        'SW-STAIR-W':[[6.325,4.625],[6.325,11.275]],
        'SW-STAIR-S':[[6.325,4.625],[9.375,4.625]],
        'SW-STAIR-N':[[6.325,11.275],[9.375,11.275]],
        'SW-SHARED-STAIR-LIFT':[[9.375,4.625],[9.375,11.275]],
        'SW-LIFT-S':[[9.375,4.625],[11.675,4.625]],
        'SW-LIFT-N':[[9.375,6.925],[11.675,6.925]],
        'SW-LIFT-E':[[11.675,4.625],[11.675,6.925]]}
    panels={name:m.psets(e)['A01_NonstructuralPanel'] for name,e in products.items()
            if e.type=='IFCWALL' and 'A01_NonstructuralPanel' in m.psets(e)}
    if revised:
        from .core_revision import horizontal_polygon
        from .rectilinear import area_weights
        levels.update({'PIT':float(geom['S-PIT']['max'][2]),
                       'STAIR_CAP':float(geom['S-STAIR-CAP']['max'][2]),
                       'LIFT_CAP':float(geom['S-LIFT-CAP']['max'][2])})
        raw_lines={}
        for name,e in products.items():
            if e.type!='IFCWALL' or not name.endswith('-1F') or name in panels:continue
            g=geom[name];axis=int(np.argmax((g['max']-g['min'])[:2]));other=1-axis
            a=g['min'][:2].copy();b=g['max'][:2].copy();a[other]=b[other]=(a[other]+b[other])/2
            raw_lines[name.rsplit('-',1)[0]]=(a,b,axis)
        wall_lines={}
        for key,(a,b,axis) in raw_lines.items():
            ends=[]
            for endpoint in (a,b):
                p=endpoint.copy();candidates=[]
                for other,(c,d,other_axis) in raw_lines.items():
                    if other_axis==axis:continue
                    if min(c[other_axis],d[other_axis])-.251<=p[other_axis]<=max(c[other_axis],d[other_axis])+.251 and abs(c[axis]-p[axis])<=.126:
                        candidates.append(float(c[axis]))
                if candidates:p[axis]=min(candidates,key=lambda v:abs(v-p[axis]))
                ends.append(p.tolist())
            wall_lines[key]=ends
        if joint_revision:
            # Physical midplane extents; explicit eccentric constraints join corners.
            wall_lines={key:[a.tolist(),b.tolist()] for key,(a,b,axis) in raw_lines.items()}
    wall_specs={};frame_owners=[];wall_sections={};ownership=[]
    if joint_revision:
        from .wall_interfaces import wall_spec, frame_bodies, mesh_breaks, remaining_normal, connect_interfaces
        wall_specs={name:wall_spec(geom[name]) for name,e in products.items()
                    if e.type=='IFCWALL' and name not in panels}
        frame_owners=frame_bodies(products,geom,m)
        for body in frame_owners:
            dimensions=body['hi']-body['lo']
            expected=(.6,.6) if body['role']=='column' else (.4,.52)
            actual=dimensions[:2] if body['role']=='column' else dimensions[[1-body['axis'],2]]
            if not np.allclose(actual,expected,rtol=0,atol=1e-8):
                raise ValueError('H03-C frame section dimensions require converter review: '+body['name'])
    web_offsets={body['name']:round(float((body['lo'][2]+body['hi'][2])/2-body['reference'][2]),7)
                 for body in frame_owners if body['role']=='beam'}
    columns_1f=[e for e in m.by_type('IFCCOLUMN') if e.args[2].endswith('-1F')]
    cols=[((geom[e.args[2]]['min']+geom[e.args[2]]['max'])/2)[:2] for e in columns_1f]
    xv=[0,18]+[p[0] for p in cols]; yv=[0,12]+[p[1] for p in cols]
    zv=[bz,0,2.,4,5.8,7.6,9.4,11.2]
    if revised:
        zv=[bz,*levels.values()]
        for name,e in products.items():
            if e.type=='IFCWALL':zv.extend([geom[name]['min'][2],geom[name]['max'][2]])
            if e.type=='IFCSTAIRFLIGHT':
                props=m.psets(e)['A01_H03_Stair'];zv.extend([props['LowerSupportZ_m'],props['UpperSupportZ_m']])
        for name,e in products.items():
            if e.type=='IFCSLAB' and name.startswith('S-'):
                p=horizontal_polygon(geom[name]);xv.extend(x for x,y in p.exterior.coords);yv.extend(y for x,y in p.exterior.coords)
    for a,b in wall_lines.values(): xv.extend([a[0],b[0]]); yv.extend([a[1],b[1]])
    for name,e in products.items():
        if e.type=='IFCOPENINGELEMENT':
            g=geom[name]; xv.extend(g['min'][[0]].tolist()+g['max'][[0]].tolist()); yv.extend(g['min'][[1]].tolist()+g['max'][[1]].tolist())
            if revised:
                footprint=horizontal_polygon(g);xv.extend(x for x,y in footprint.exterior.coords);yv.extend(y for x,y in footprint.exterior.coords)
            if 'DOOR' in name: zv.extend([g['min'][2],g['max'][2]])
    # Stair load-transfer stations (no stair stiffness in this global model).
    if revised:
        for e in m.by_type('IFCSTAIRFLIGHT'):
            p=m.psets(e)['A01_H03_Stair'];yv.extend([p['LowerSupportY_m'],p['UpperSupportY_m']])
        for name in panels:
            g=geom[name];centre=(g['min']+g['max'])/2;xv.append(centre[0]);yv.append(centre[1])
    else:yv.extend([6.15,9.75,11.15])
    if joint_revision:
        extra=mesh_breaks(wall_specs,frame_owners)
        xv.extend(extra[0]);yv.extend(extra[1]);zv.extend(extra[2])
        for body in frame_owners:
            if body['role']=='column':
                xv.extend([body['lo'][0],body['hi'][0]])
                yv.extend([body['lo'][1],body['hi'][1]])
    xv=[v for v in xv if 0<=v<=18]; yv=[v for v in yv if 0<=v<=12]
    X=subdivide(xv,h); Y=subdivide(yv,h); Z=subdivide(zv,h)
    nodes=[]; ids={}; els=[]; mapped=defaultdict(list); shellinfo={}; loads=defaultdict(lambda:defaultdict(lambda:np.zeros(6))); mass=defaultdict(float); ledger=[]
    gamma=cfg['materials']['unit_weight_kN_m3']; grav=cfg['materials']['g_m_s2']; L=cfg['loads']
    def node(x,y,z):
        # H03-C receiving coordinates retain the eight-decimal mesh stations.
        # Rounding them to seven decimals changes integrated load first moments.
        key=tuple(round(float(a),10 if joint_revision else 7) for a in [x,y,z])
        if key not in ids: ids[key]=len(nodes)+1; nodes.append({'id':len(nodes)+1,'xyz':list(key)})
        return ids[key]
    def element(kind,ns,sec,name,**kw):
        e={'id':len(els)+1,'kind':kind,'nodes':ns,'section':sec,'source_name':name,'source_guid':products[name].args[0],**kw}
        els.append(e); mapped[name].append(e); return e
    def gravity(case,nodes_,W,add_mass=False,weights=None):
        if not revised:
            # Preserve the adopted H02 operation order, including roundoff.
            for nid in nodes_:
                loads[case][nid][2]-=W/len(nodes_)
                if add_mass:mass[nid]+=W/len(nodes_)/grav
            return
        if W<=1e-14:return
        weights=np.ones(len(nodes_))/len(nodes_) if weights is None else np.asarray(weights,float)
        if min(weights)<-1e-8 or abs(sum(weights)-1)>1e-8:raise ValueError('Invalid gravity distribution')
        for nid,factor in zip(nodes_,weights):
            loads[case][nid][2]-=W*factor
            if add_mass: mass[nid]+=W*factor/grav
    def source_gross_net(name):
        g=geom[name]; vol=g['volume']
        for on in voids[name]:
            a,b=geom[on]['min'],geom[on]['max']; dims=np.maximum(0,np.minimum(g['max'],b)-np.maximum(g['min'],a)); vol-=float(np.prod(dims))
        return vol
    # Floor shells and spatial gravity / live load inputs. No ground-floor shell.
    floor_names=['S-2F','S-3F','S-RF']+(['S-STAIR-CAP','S-LIFT-CAP','S-PIT'] if revised else [])
    floor_cells={}
    for name in floor_names:
        lv=name[2:];z=float(geom[name]['max'][2]);thickness=float(geom[name]['max'][2]-geom[name]['min'][2])
        footprint=horizontal_polygon(geom[name]) if revised else box(0,0,18,12)
        holes=[horizontal_polygon(geom[v]) if revised else box(*geom[v]['min'][:2],*geom[v]['max'][:2]) for v in voids[name]]
        hole=unary_union(holes)
        occupied=[]
        for pn,g in geom.items():
            if products[pn].type in ['IFCCOLUMN','IFCWALL'] and g['min'][2]<z-1e-6 and g['max'][2]>=z-1e-6:
                occupied.append(box(*g['min'][:2],*g['max'][:2]))
        excluded=unary_union(occupied)
        selfW=liveW=0
        for x1,x2 in zip(X[:-1],X[1:]):
            for y1,y2 in zip(Y[:-1],Y[1:]):
                poly=box(x1,y1,x2,y2); area=poly.area
                if not footprint.covers(poly.representative_point()):continue
                if poly.difference(footprint).area>1e-8:raise ValueError('Non-conforming slab boundary')
                if hole.contains(poly.representative_point()): continue
                if abs(poly.intersection(hole).area)>1e-8: raise ValueError('Non-conforming slab-opening mesh')
                ns=[node(x1,y1,z),node(x2,y1,z),node(x2,y2,z),node(x1,y2,z)]
                el=element('shell',ns,'pit' if name=='S-PIT' else 'floor',name,role='floor'); shellinfo[el['id']]={'area':area,'polygon':poly}
                floor_cells.setdefault(name,[]).append((poly,ns))
                net=poly.difference(excluded)
                netarea=max(0,net.area if revised else area-poly.intersection(excluded).area)
                factors=area_weights(net,poly.bounds)/netarea if revised and netarea>1e-12 else None
                W=netarea*(thickness if revised else .18)*gamma; gravity('D_SELF',ns,W,True,factors); selfW+=W
                pressure=(0. if name=='S-PIT' else equipment['roof']['cap_finish_kN_m2']
                          if revised and name.endswith('-CAP') else L['finishes_and_general_mep_kN_m2'])
                gravity('D_SUPER',ns,netarea*pressure,True,factors)
                if lv in ('2F','3F'):
                    gravity('L_OFFICE',ns,netarea*L['office_kN_m2'],False,factors); liveW+=netarea*L['office_kN_m2']
                    gravity('L_PARTITION',ns,netarea*L['movable_partition_kN_m2'],True,factors)
                elif name!='S-PIT': gravity('L_ROOF',ns,netarea*L['roof_kN_m2'],False,factors)
                if lv==L['local_patch_floor']:
                    cx,cy=L['local_patch_center_m']; wx,wy=L['office_local_patch_size_m']
                    overlap=poly.intersection(box(cx-wx/2,cy-wy/2,cx+wx/2,cy+wy/2)).area
                    if overlap>0:
                        patch=poly.intersection(box(cx-wx/2,cy-wy/2,cx+wx/2,cy+wy/2))
                        gravity('L_POINT_SINGLE',ns,overlap/(wx*wy)*L['office_local_patch_kN'],False,
                                area_weights(patch,poly.bounds)/overlap if revised else None)
        ledger.append({'source':name,'self_weight_kN':selfW,'note':'slab openings, column and wall footprint intersections removed from self weight; not area loads on ground slab'})
        if name not in ('S-2F','S-3F','S-RF'):continue
        # Nonstructural façade/parapet gravity transferred to perimeter frame lines.
        lineweight=L['external_wall_line_load_kN_m']+(L['parapet_line_load_kN_m'] if lv=='RF' else 0)
        for axis,fixedv,lo,hi in [('X',.3,.3,17.7),('X',11.7,.3,17.7),('Y',.3,.3,11.7),('Y',17.7,.3,11.7)]:
            vals=[v for v in (X if axis=='X' else Y) if lo-1e-8<=v<=hi+1e-8]
            # Preserve 18m /12m exterior length total while using perimeter beam centreline.
            scale=(18/(hi-lo)) if axis=='X' else (12/(hi-lo))
            for a,b in zip(vals[:-1],vals[1:]):
                ns=[node(a,fixedv,z),node(b,fixedv,z)] if axis=='X' else [node(fixedv,a,z),node(fixedv,b,z)]
                gravity('D_SUPER',ns,(b-a)*lineweight*scale,True)
    # Continuous columns, including free below-grade segments.
    for e in m.by_type('IFCCOLUMN'):
        name=e.args[2]; g=geom[name]; x,y=((g['min']+g['max'])/2)[:2]; za,zb=g['min'][2],g['max'][2]
        zs=[z for z in Z if za-1e-8<=z<=zb+1e-8] if revised else subdivide([za,zb],h)
        for a,b in zip(zs[:-1],zs[1:]):
            ns=[node(x,y,a),node(x,y,b)]; element('frame',ns,'column',name,role='column',local_y=[1.,0.,0.],offset=[0.,0.,0.])
            gravity('D_SELF',ns,.6*.6*(b-a)*gamma,True)
        ledger.append({'source':name,'self_weight_kN':g['volume']*gamma,'note':'gross column segments; vertical overlap removed from slab self weight'})
    # Main beams: web below slab + eccentric rigid offset to slab reference plane.
    # This avoids counting the slab flange a second time as a full rectangular beam.
    colpos={e.args[2]:((geom[e.args[2]]['min']+geom[e.args[2]]['max'])/2)[:2] for e in m.by_type('IFCCOLUMN')}
    for e in m.by_type('IFCBEAM'):
        name=e.args[2]; g=geom[name]; pset=m.psets(e)['A01_MainBeam']
        c1=np.array(colpos[pset['StartColumn']]); c2=np.array(colpos[pset['EndColumn']]); z=g['max'][2]
        axis=0 if abs(c2[0]-c1[0])>1e-6 else 1; other=1-axis; lo,hi=sorted([c1[axis],c2[axis]])
        vals=[v for v in (X if axis==0 else Y) if lo-1e-7<=v<=hi+1e-7]
        physical_lo=g['min'][axis]; physical_hi=g['max'][axis]; Wsum=0
        for a,b in zip(vals[:-1],vals[1:]):
            p=c1.copy(); q=c1.copy(); p[axis]=a; q[axis]=b
            ns=[node(*p,z),node(*q,z)]
            locy=[0.,1.,0.] if axis==0 else [-1.,0.,0.]
            element('frame',ns,'beam_web',name,role='beam',local_y=locy,
                    offset=[0.,0.,web_offsets[name] if joint_revision else -.35])
            weighted_length=max(0,min(b,physical_hi)-max(a,physical_lo)); W=weighted_length*.4*(.70-.18)*gamma
            factors=None
            if revised and weighted_length>0:
                centre=(max(a,physical_lo)+min(b,physical_hi))/2;factors=[(b-centre)/(b-a),(centre-a)/(b-a)]
            gravity('D_SELF',ns,W,True,factors); Wsum+=W
        ledger.append({'source':name,'self_weight_kN':Wsum,'note':'clear-span web weight only; flange already in slab; local joint overlap not quantity-certified'})
    # Core walls: conforming shell mesh, door voids omitted, corners joined.
    for e in m.by_type('IFCWALL'):
        if e.args[2] in panels:continue
        name=e.args[2]; key=name.rsplit('-',1)[0]; g=geom[name]; a,b=np.array(wall_lines[key],float)
        axis=0 if abs(a[0]-b[0])>1e-8 else 1; other=1-axis
        tv=[v for v in (X if axis==0 else Y) if min(a[axis],b[axis])-1e-8<=v<=max(a[axis],b[axis])+1e-8]
        zs=[v for v in Z if g['min'][2]-1e-8<=v<=g['max'][2]+1e-8]
        records=[]; total_area=0
        for u,v in zip(tv[:-1],tv[1:]):
            for z1,z2 in zip(zs[:-1],zs[1:]):
                mid=np.array([(u+v)/2,(z1+z2)/2]); skip=False
                for hole_name in voids[name]:
                    og=geom[hole_name]
                    if og['min'][axis]-1e-8<mid[0]<og['max'][axis]+1e-8 and og['min'][2]-1e-8<mid[1]<og['max'][2]+1e-8: skip=True
                if skip: continue
                strips=remaining_normal(wall_specs[name],frame_owners,u,v,z1,z2) if joint_revision else [(0.,.25)]
                for normal_lo,normal_hi in strips:
                    points=[];thickness=normal_hi-normal_lo
                    section=f'wall_owned_{thickness:.7f}' if joint_revision else 'wall'
                    if joint_revision:wall_sections[section]={'t':thickness,'E_factor':1.0}
                    for s,z in [(u,z1),(v,z1),(v,z2),(u,z2)]:
                        xy=a.copy();xy[axis]=s
                        if joint_revision:xy[other]=(normal_lo+normal_hi)/2
                        points.append(node(*xy,z))
                    el=element('shell',points,section,name,role='wall')
                    area=(v-u)*(z2-z1);records.append((el,area));total_area+=area
                    if joint_revision:
                        gravity('D_SELF',points,area*thickness*gamma,True)
                        ownership.append({'source_name':name,'source_guid':e.args[0],
                            'element':el['id'],'axis':axis,'normal_interval_m':[normal_lo,normal_hi],
                            'axis_interval_m':[u,v],'z_interval_m':[z1,z2],
                            'owned_volume_m3':area*thickness})
        if not records: raise ValueError(f'Empty wall {name}')
        W=(sum(area*wall_sections[el['section']]['t'] for el,area in records)
           if joint_revision else source_gross_net(name))*gamma
        if not joint_revision:
            for el,area in records: gravity('D_SELF',el['nodes'],W*area/total_area,True)
        ledger.append({'source':name,'self_weight_kN':W,
                       'note':('Physical wall concrete after column/clear-span beam-web ownership; exact cell centroids'
                               if joint_revision else 'physical wall net volume (door subtracted) distributed over connected midplane mesh')})
    from .stair_transfer import apply_stairs
    stair_transfer=apply_stairs(m,products,geom,voids,nodes,els,loads,mass,ledger,gamma,grav,
                               L['stairs_kN_m2'],scheme['finishes']['stair_finish_and_rail_kN_m2'],
                               owned_wall_cells=joint_revision)
    (outdir/'stair_transfer.json').write_text(json.dumps(stair_transfer,indent=2))
    core_loads=None
    if revised:
        from .core_loads import apply_core_loads
        core_loads=apply_core_loads(m,products,geom,voids,floor_cells,panels,equipment,gravity,ledger,grav)
        (outdir/'core_loads.json').write_text(json.dumps(core_loads,indent=2))
    # Explicitly labelled lateral stiffness experiments: total = 100 kN, not
    # earthquake/wind design forces. Three floor forces proportional to z above base.
    for lv in ['2F','3F','RF']:
        if joint_revision:
            F=L['lateral_calibration_total_kN']*(levels[lv]-bz)/sum(levels[l]-bz for l in ['2F','3F','RF'])
            cells=floor_cells['S-'+lv];area=sum(poly.area for poly,ns in cells)
            for poly,ns in cells:
                for n in ns:
                    for ax,key in [(0,'X100_CALIBRATION'),(1,'Y100_CALIBRATION')]:
                        loads[key][n][ax]+=F*poly.area/area/4
            continue
        z=levels[lv]; levelnodes=[n['id'] for n in nodes if abs(n['xyz'][2]-z)<1e-7 and mass[n['id']]>0]
        W=sum(mass[n] for n in levelnodes)
        F=L['lateral_calibration_total_kN']*(z-bz)/sum(levels[l]-bz for l in ['2F','3F','RF'])
        for n in levelnodes:
            for ax,key in [(0,'X100_CALIBRATION'),(1,'Y100_CALIBRATION')]: loads[key][n][ax]+=F*mass[n]/W
    for name in ['D_SELF','D_SUPER','L_OFFICE','L_PARTITION','L_ROOF','L_STAIRS']+(['D_PANEL','D_EQUIPMENT','L_LIFT'] if revised else []):
        for n,v in loads[name].items(): loads['SERVICE_ILLUSTRATION'][n]+=v
    if revised:
        # Replace the complete normal lift system with each alternative envelope.
        for case,extra in [('SERVICE_LIFT_HEAD','LIFT_HEAD_ENVELOPE'),('SERVICE_LIFT_BUFFER','LIFT_BUFFER_ENVELOPE')]:
            for n,v in loads['SERVICE_ILLUSTRATION'].items():loads[case][n]+=v
            for r in core_loads['records']:
                if r['label'] in ('lift_permanent','lift_payload'):
                    for n in r['receiving_nodes']:loads[case][n['node']][2]+=n['downward_kN']
            for n,v in loads[extra].items():loads[case][n]+=v
    finish=scheme['finishes']['stair_finish_and_rail_kN_m2']
    bounds=scheme['finishes']['stair_finish_sensitivity_kN_m2']
    if len(bounds)!=2 or not (0<bounds[0]<finish<bounds[1]):
        raise ValueError('Stair finish sensitivity must bracket the adopted positive allowance')
    for case,pressure in zip(['SERVICE_STAIR_FINISH_LOW','SERVICE_STAIR_FINISH_HIGH'],bounds):
        for n,v in loads['SERVICE_ILLUSTRATION'].items(): loads[case][n]+=v
        for source_record in stair_transfer['sources']:
            component=next(c for c in source_record['components'] if c['case']=='D_SUPER')
            for r in component['receiving_nodes']:
                loads[case][r['node']][2]-=r['downward_kN']*(pressure/finish-1)
    rigid_joints=[];joint_audit=None
    if joint_revision:
        rigid_joints,joint_audit=connect_interfaces(nodes,els,wall_specs,frame_owners,bz)
        (outdir/'joint_interfaces.json').write_text(json.dumps(joint_audit,indent=2))
        (outdir/'concrete_ownership.json').write_text(json.dumps({
            'priority':['columns','clear_span_beam_webs','walls','floor_self_weight'],
            'wall_cells':ownership,'physical_geometry_changed':False,
            'scope':'Concrete accounting and gross elastic joint idealization; not reinforcement or priced quantities'},indent=2))
    # Verify connections through elements and explicit, later solver-verified MPCs.
    parent=list(range(len(nodes)+1))
    def find(a):
        while parent[a]!=a: parent[a]=parent[parent[a]]; a=parent[a]
        return a
    used=set()
    for e in els:
        for a in e['nodes']: parent[find(a)]=find(e['nodes'][0]); used.add(a)
    for link in rigid_joints:
        parent[find(link['slave'])]=find(link['master'])
    components=len({find(i) for i in used}); orphans=sorted(set(range(1,len(nodes)+1))-used)
    if components!=1 or orphans: raise ValueError(f'Topology error: {components} components, orphan nodes {orphans[:10]}')
    supports=[{'node':n['id'],'fixity':[1]*6,'basis':'TRIAL_FIXED_BASE_NOT_FOUNDATION_DESIGN'} for n in nodes if abs(n['xyz'][2]-bz)<1e-7]
    def rectangle(b,d):
        a=max(b,d); t=min(b,d); J=a*t**3*(1/3-.21*(t/a)*(1-t**4/(12*a**4)))
        return {'A':b*d,'Iy':b*d**3/12,'Iz':d*b**3/12,'J':J,'b':b,'h':d,'E_factor':1.0}
    metadata={'project':'A01','revision':cfg['revision'],'schema':'a01-linear-analysis-1.0',
        'architectural_scheme_sha256':hashlib.sha256(Path(architect_scheme).read_bytes()).hexdigest(),
        'stair_transfer_method':stair_transfer['method'],
        'source_ifc_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        'physical_ifc':physical_name,'source_ifc':Path(source).name,
        'status':'ANALYSIS_INPUT_NOT_DESIGN_APPROVAL','units':cfg['units'],'base_elevation_m':bz,
        'levels_m':levels,'materials':cfg['materials'],'sections':{'column':rectangle(.6,.6),'beam_web':rectangle(.4,.52),'floor':{'t':.18,'E_factor':1.0},'wall':{'t':.25,'E_factor':1.0}},
        'nodes':nodes,'elements':els,'supports':supports,'drilling_penalty':1e-4,
        'nodal_masses':[{'node':n,'mass':[v,v,v,0.,0.,0.]} for n,v in sorted(mass.items()) if v>1e-12],
        'load_cases':{key:{'description':('Unfactored service illustration, NOT a code strength combination' if key=='SERVICE_ILLUSTRATION' else 'Unit stiffness calibration only: NOT wind/seismic demand' if 'CALIBRATION' in key else key),
            'nodal_loads':[{'node':n,'vector':v.tolist()} for n,v in sorted(items.items()) if np.linalg.norm(v)>1e-12]} for key,items in loads.items()},
        'mapping':{k:{'ifc_guid':products[k].args[0],'analytical_elements':[e['id'] for e in v]} for k,v in mapped.items()},
        'load_only_mapping':{s['source_name']:{'ifc_guid':s['source_guid'],
                            'receiving_nodes':sorted({n['node'] for c in s['components'] for n in c['receiving_nodes']}),
                            'detail':'stair_transfer.json'} for s in stair_transfer['sources']},
        'explicit_idealizations':['H03-B candidate core revision; main frame retained from R05.' if revised else 'Physical geometry above 0.0m unchanged from R05.',
            'Walls represented by joined midplanes, with door holes explicitly absent from mesh.',
            'Slab reference plane placed at storey elevation; no 90mm global shift applied.',
            'Beam web below slab: 400x520mm with -0.35m eccentric offset to floor plane; slab flange is a shell.',
            'No rigid end zones / no moment releases in main frame joints.',
            'No ground-floor diaphragm or ground-level fixity; no soil springs.',
            'Stairs contribute equivalent gravity load and mass only, no stiffness.',
            'Wall geometry/self weight derived from source; floor self weight excludes column/wall footprint overlap.',
            'Cracking, P-delta and nonlinearities omitted. Unknown equipment loads remain unresolved.'],
        'limitations':cfg['limitations']}
    if revised:
        metadata['sections']['pit']={'t':float(geom['S-PIT']['max'][2]-geom['S-PIT']['min'][2]),'E_factor':1.0}
        metadata['equipment_basis_sha256']=hashlib.sha256(Path(equipment_basis).read_bytes()).hexdigest()
        metadata['load_only_mapping'].update({name:{'ifc_guid':products[name].args[0],
            'receiving_nodes':sorted({n['node'] for r in core_loads['records'] if r['label']==name for n in r['receiving_nodes']}),
            'detail':'core_loads.json'} for name in panels})
        metadata['explicit_idealizations'].append('Synthetic equipment patches and load-only lightweight panels; impact excluded from mass. Ground panel weight retained separately for future foundation input.')
    if joint_revision:
        metadata['rigid_joints']=rigid_joints
        metadata['sections'].update(wall_sections)
        metadata['joint_method']=joint_audit['method']
        metadata['explicit_idealizations']=[v for v in metadata['explicit_idealizations']
            if not v.startswith(('Walls represented','Beam web below','No rigid end','H03-B'))]
        metadata['explicit_idealizations'].extend([
            'H03-C retains the H03-B physical source and regular main frame.',
            'Columns and clear-span beam webs own shared concrete before wall shells; remaining wall strips use actual thickness and midplane.',
            'Small-rotation rigid cross-section/contact groups join columns, beams, walls and wall corners; short rigid joint zones are explicit in joint_interfaces.json.',
            'Beam web 400x520 mm occupies -0.70..-0.18 m below SSL; centroid offset -0.44 m corrects the inherited -0.35 m full-depth offset.',
            '100 kN calibration uses uniform source-floor area distribution; resultant moments are independent of mesh and nodal mass placement.',
            'Joint bond slip, finite panel-zone shear deformation, cracking and local concrete/reinforcement stress recovery are not represented.'])
    (outdir/'analytical_model.json').write_text(json.dumps(metadata,indent=2))
    (outdir/'load_ledger.json').write_text(json.dumps(ledger,indent=2))
    stat={'physical_counts':{typ:len(m.by_type(typ)) for typ in ['IFCCOLUMN','IFCBEAM','IFCWALL','IFCSLAB','IFCSTAIRFLIGHT']},
          'nodes':len(nodes),'elements':len(els),'frame_elements':sum(e['kind']=='frame' for e in els),'shell_elements':sum(e['kind']=='shell' for e in els),
          'support_nodes':len(supports),'connected_components':components,'orphan_nodes':orphans,
          'below_grade_column_segments':12,'below_grade_wall_segments':7,
          'grade_nodes_fixed':False,'minimum_elevation_m':min(n['xyz'][2] for n in nodes),
          'all_references_resolve':True,'full_IFC_EXPRESS_validation':False,'Bonsai_import':False,
          'OpenSees_execution':'NOT_RUN',
          'load_resultants_kN':{k:np.array([ld['vector'] for ld in c['nodal_loads']]).sum(0).tolist() for k,c in metadata['load_cases'].items()}}
    (outdir/'model_checks.json').write_text(json.dumps(stat,indent=2))
    print(json.dumps(stat,indent=2)); return metadata
