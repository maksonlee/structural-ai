"""Draw two case-specific structural interface review sheets from verified inputs."""
import argparse
import json
from pathlib import Path
import numpy as np
from shapely.geometry import box, Point
from structural_ai.coordination import Sheet, read_geometry
from structural_ai.provenance import file_hash, write_json


def draw(source, verification, out):
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((verification/'manifest.json').read_text())
    if not manifest['status'].startswith('COMPLETED_CANDIDATE_DIAGNOSTICS'):
        raise ValueError('Interface sheets require a completed candidate verification')
    for name,digest in manifest['output_sha256'].items():
        if file_hash(verification/name)!=digest:
            raise ValueError('Verification output changed before drawing: '+name)
    model_path=verification/'baseline-build/analytical_model.json'
    model=json.loads(model_path.read_text())
    if model['revision']!='H03-C' or model['source_ifc_sha256']!=file_hash(source):
        raise ValueError('Drawing source differs from the verified H03-C model')
    audit=json.loads((verification/'connections.json').read_text())
    result=json.loads((verification/'baseline-analysis/results/summary.json').read_text())
    if not audit['passed'] or not result['diagnostic_checks_passed']:
        raise ValueError('Incomplete interface or solver checks')
    _,objects,_,_,_,_=read_geometry(source)
    # These are deliberately A01 detail views, not a generic drawing generator.
    # Reject a changed physical section before reusing their crop/dimension labels.
    expected={
        'SW-STAIR-W-1F':([6.12,3.5,0.],[6.37,11.68,4.]),
        'C-B2-1F':([5.7,3.9,0.],[6.3,4.5,4.]),
        'C-B3-1F':([5.7,11.4,0.],[6.3,12.,4.]),
        'B-Y-B-23-2F':([5.8,4.5,3.3],[6.2,11.4,4.]),
    }
    for name,(lo,hi) in expected.items():
        if not np.allclose([objects[name]['min'],objects[name]['max']],[lo,hi],rtol=0,atol=1e-8):
            raise ValueError('Review source section before drawing '+name)
    if not np.isclose(objects['S-2F']['max'][2]-objects['S-2F']['min'][2],.18,rtol=0,atol=1e-8):
        raise ValueError('Review slab flange before drawing')
    out.mkdir(parents=True,exist_ok=False)
    digest=file_hash(source);xyz={n['id']:np.array(n['xyz']) for n in model['nodes']}
    sheet=Sheet('SR-001','Wall-column concrete ownership and force-transfer review',digest,'CASE STUDY',
                'Architectural model / verified structural interfaces')
    sheet.text(14,33,'Same physical frame and core. Coloured partitions identify concrete ownership; they do not change member outlines.',2.8)
    for index,(grid,ymin) in enumerate((('B2',3.4),('B3',11.15))):
        ox=18+index*205
        tr=lambda x,y,ox=ox,ymin=ymin:(ox+(x-5.4)*100,205-(y-ymin)*100)
        sheet.text(ox,47,grid+' PLAN / 1:10 / analytical slice z = +2.00 m',2.8)
        wall=objects['SW-STAIR-W-1F'];column=objects['C-'+grid+'-1F']
        clip=box(5.4,ymin,7.0,ymin+1.5)
        wall_shape=box(*wall['min'][:2],*wall['max'][:2]).intersection(clip)
        col_shape=box(*column['min'][:2],*column['max'][:2])
        sheet.shape(wall_shape.difference(col_shape),tr,'#b8dcca','#287457',guid=wall['guid'])
        if grid=='B3':
            north=objects['SW-STAIR-N-1F']
            sheet.shape(box(*north['min'][:2],*north['max'][:2]).intersection(clip),tr,'#b8dcca','#287457',guid=north['guid'])
        else:
            sheet.shape(box(6.12,4.6,6.37,4.9),tr,'white','#287457')
        sheet.shape(col_shape,tr,'#486777','#163b50',guid=column['guid'])
        sheet.shape(wall_shape.intersection(col_shape),tr,'#eeb369','#95601d')
        cx,cy=(np.array(column['min'][:2])+np.array(column['max'][:2]))/2
        sheet.text(*tr(cx-.16,cy+.03),grid,3.5,'white')
        sheet.line(*tr(6.0,ymin),*tr(6.0,ymin+1.5),'#5b8fb0',.2,'1,1')
        master=next(node for node,p in xyz.items() if np.allclose(p,[cx,cy,2.],rtol=0,atol=1e-7))
        contacts=[link for link in model['rigid_joints'] if link['master']==master
                  and abs(xyz[link['slave']][2]-2.)<1e-7 and xyz[link['slave']][0]>6.30]
        selected=sorted(contacts,key=lambda link:xyz[link['slave']][1])
        selected=[selected[i] for i in sorted({0,len(selected)//2,len(selected)-1})] if selected else []
        for link in selected:
            p=xyz[link['slave']]
            sheet.line(*tr(cx,cy),*tr(*p[:2]),'#ae3858',.35,'1,1')
            sheet.shape(Point(*p[:2]).buffer(.012),tr,'#ae3858','#ae3858')
        sheet.text(ox,215,'Blue: column-owned; orange: shared volume counted in column.',2.25)
        sheet.text(ox,222,'Green: remaining wall; magenta: selected eccentric constraint links.',2.25)
        sheet.text(ox,229,'Wall x = 6.12..6.37; remaining strip x = 6.30..6.37 m.',2.45)
        sheet.text(ox,236,'Column axis x = 6.00; remaining wall midplane x = 6.335 m.',2.45)
    sheet.text(18,248,'The 70 mm strip belongs to one monolithic wall-column section; it is not a separate proposed thin wall.',2.75,'#a14428')
    sheet.text(18,256,'B2 north face y = 4.50; portal starts y = 4.60. Finished portal width remains 1.28 m.',2.75)
    sheet.text(18,264,'Elastic contact forces are available in case_joint_actions.csv. Bond slip, joint shear flexibility and RC reinforcement remain open.',2.6)
    sheet.write(out/'wall-column-detail.svg')

    sheet=Sheet('SR-002','Beam-wall section, diagnostic results and remaining design gates',digest,'CASE STUDY',
                'Architectural model / verified structural interfaces')
    sheet.text(14,33,'Section through the B-line rear-bay beam at 2F. Concrete outlines are unchanged; the analytical web centroid is corrected.',2.7)
    tr=lambda x,z:(22+(x-5.4)*105,194-(z-3.1)*105)
    sheet.text(22,48,'B-Y-B-23-2F / transverse section / 1:9.52',2.8)
    beam=objects['B-Y-B-23-2F'];slab=objects['S-2F'];west=objects['SW-STAIR-W-1F']
    wall=box(west['min'][0],3.1,west['max'][0],4.2)
    web=box(beam['min'][0],beam['min'][2],beam['max'][0],slab['min'][2])
    sheet.shape(wall.difference(web),tr,'#b8dcca','#287457')
    sheet.shape(box(5.4,3.82,6.12,4.),tr,'#d0e4f0','#507e9a')
    sheet.shape(web,tr,'#eeb369','#95601d')
    sheet.line(*tr(5.4,4.),*tr(6.7,4.),'#507e9a',.25,'1,1')
    sheet.text(*tr(6.42,4.02),'SSL +4.00',2.8)
    sheet.line(*tr(5.7,3.56),*tr(6.32,3.56),'#ae3858',.35,'1,1')
    sheet.text(*tr(6.42,3.58),'Web centre +3.56',2.8,'#ae3858')
    sheet.text(*tr(6.42,3.33),'Soffit +3.30',2.8)
    sheet.text(22,210,'Web: 0.40 x 0.52 m; centroid 0.44 m below SSL.',2.8)
    sheet.text(22,218,'Slab flange: 0.18 m; no second full-depth beam section.',2.65)
    sheet.text(22,226,'Beam-owned overlap leaves 0.17 m wall at this section.',2.65)
    sheet.text(22,234,'Remaining wall midplane x = 6.285 m; corner/contact offsets are explicit.',2.45)
    quantities=audit['intersection_volume_by_owner_m3'];total=audit['removed_wall_frame_overlap_m3']
    lines=['ACCOUNTING CORRECTION',
           f"Wall / column: {quantities['IFCCOLUMN']:.5f} m3",
           f"Wall / beam web: {quantities['IFCBEAM']:.5f} m3",
           f'Total counted once: {total:.5f} m3 / {total*model["materials"]["unit_weight_kN_m3"]:.5f} kN',
           'This is duplicated accounting removed, not physical concrete saved.',
           '', 'DIAGNOSTIC ANALYSIS RESULTS',
           f"Service gravity: {-result['cases']['SERVICE_ILLUSTRATION']['applied_force_kN'][2]:.3f} kN",
           f"Max vertical displacement: {result['cases']['SERVICE_ILLUSTRATION']['max_abs_translation_mm'][2]:.4f} mm",
           f"X100 / Y100: {result['cases']['X100_CALIBRATION']['max_abs_translation_mm'][0]:.5f} / {result['cases']['Y100_CALIBRATION']['max_abs_translation_mm'][1]:.5f} mm",
           f"First period: {result['modes'][0]['period_s']:.6f} s",
           f"Direct wall-frame intersections: {len(audit['frame_contacts'])}; MPCs: {len(model['rigid_joints'])}",
           '', 'REMAINING DESIGN',
           'Code wind/earthquake and combinations; cracking and system checks;',
           'all-member reinforcement, stairs/joints and anchorage;',
           'soil/foundations, coherent bar drawings and schedules;',
           'priced quantities, congestion and construction feasibility.']
    for i,line in enumerate(lines):sheet.text(218,51+i*10,line,2.65,'#a14428' if i in (4,13) else '#183848')
    sheet.text(22,249,'100 kN cases use uniform floor-area distribution, independent of mesh mass. They are not wind or earthquake actions.',2.65)
    sheet.text(22,258,'The -1.80 m fixed base is diagnostic. Synthetic equipment inputs and uncracked elastic stiffness are not final design criteria.',2.65)
    sheet.text(22,267,'Use with AR-001/002 and the structural report. These are coordination/review sheets; reinforcement is not drawn or approved.',2.6)
    sheet.write(out/'beam-wall-detail.svg')
    names=['wall-column-detail.svg','beam-wall-detail.svg']
    (out/'wall-interface-review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Structural interface review</title><style>@page{size:A3 landscape;margin:0}body{margin:0}img{display:block;width:420mm;height:297mm;break-after:page}</style>'+''.join(f'<img src="{name}" alt="{name}">' for name in names)+'</html>')
    write_json(out/'drawing-inputs.json',{'source_sha256':digest,'analytical_model_sha256':file_hash(model_path),
        'verification_run_id':verification.name,'solver_version':result['version'],
        'inputs':[p.resolve().relative_to(root).as_posix() for p in (source,model_path,verification/'connections.json')],
        'output_sha256':{name:file_hash(out/name) for name in names},'engineering_approval':False})
    return names


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--verification',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(draw(args.source,args.verification,args.output))
