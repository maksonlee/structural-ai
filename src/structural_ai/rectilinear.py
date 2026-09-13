"""Exact area/first-moment transfer for A01's orthogonal plan regions."""
import numpy as np
from shapely.geometry import box


def rectangles(region):
    if region.is_empty:
        return []
    pieces = list(region.geoms) if region.geom_type == 'MultiPolygon' else [region]
    result = []
    for p in pieces:
        if p.geom_type != 'Polygon' or not p.is_valid:
            raise ValueError('Expected valid orthogonal polygons')
        rings = [p.exterior, *p.interiors]
        coordinates = [xy for r in rings for xy in r.coords]
        for r in rings:
            for a,b in zip(r.coords,list(r.coords)[1:]):
                if abs(a[0]-b[0])>1e-9 and abs(a[1]-b[1])>1e-9:
                    raise ValueError('Non-orthogonal region requires a different load integration')
        xs,ys=[sorted(set(round(x[i],10) for x in coordinates)) for i in (0,1)]
        for a,b in zip(xs,xs[1:]):
            for c,d in zip(ys,ys[1:]):
                rect=box(a,c,b,d)
                if p.covers(rect.representative_point()):result.append(rect)
    if not np.isclose(sum(r.area for r in result),region.area,rtol=1e-8,atol=1e-9):
        raise ValueError('Rectangular integration lost area')
    return result


def area_weights(region, bounds):
    """Integrals of four bilinear shape functions, ordered SW, SE, NE, NW.

    Orthogonal clipping is decomposed into rectangles; centroid quadrature is
    exact for each bilinear function on each rectangle. No solver is implemented.
    """
    x0,y0,x1,y1=bounds
    if x1<=x0 or y1<=y0 or region.difference(box(*bounds)).area>1e-8:
        raise ValueError('Region lies outside its receiving cell')
    result=np.zeros(4)
    for p in rectangles(region):
        u=(p.centroid.x-x0)/(x1-x0);v=(p.centroid.y-y0)/(y1-y0)
        result+=p.area*np.array([(1-u)*(1-v),u*(1-v),u*v,(1-u)*v])
    if min(result)<-1e-9 or abs(sum(result)-region.area)>1e-8:
        raise ValueError('Invalid integrated area weights')
    return result
