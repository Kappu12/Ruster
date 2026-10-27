"""Screen-space wire picking, independent of Blender's surface/gizmo picking."""
import math


def clip_segment(a,b):
    """Clip homogeneous endpoints before dividing, including the near plane.

    Projecting a behind-eye endpoint first produces enormous or mirrored edges
    when navigating inside a volume. Use the same six clip planes as drawing.
    """
    start,end=0.,1.
    for axis,sign in ((0,1),(0,-1),(1,1),(1,-1),(2,1),(2,-1)):
        fa=a[3]+sign*a[axis];fb=b[3]+sign*b[axis]
        if fa<0 and fb<0:return None
        if fa<0:start=max(start,fa/(fa-fb))
        elif fb<0:end=min(end,fa/(fa-fb))
        if start>end:return None
    points=[tuple(x+(y-x)*t for x,y in zip(a,b)) for t in (start,end)]
    if any(p[3]<=1e-8 for p in points):return None
    return points


def project_segment(a,b,width,height):
    clipped=clip_segment(a,b)
    if clipped is None:return None
    return [((p[0]/p[3]+1)*width/2,(p[1]/p[3]+1)*height/2,p[2]/p[3]) for p in clipped]


def edge_distance(point,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    length=dx*dx+dy*dy
    t=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)) if length else 0.
    return math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy),a[2]+t*(b[2]-a[2])


def wire_hit(point,segments,radius):
    """Return distance/depth of the closest boundary; empty interiors miss."""
    hits=(edge_distance(point,a,b) for a,b in segments)
    hit=min(hits,default=(math.inf,math.inf))
    return hit if hit[0]<=radius else None
