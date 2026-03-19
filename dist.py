import math

def coords(dist, angle):
    angle_rad = math.radians(angle)
    x_obj = round(dist * math.cos(angle_rad), 3)
    y_obj = round(dist * math.sin(angle_rad), 3)
    return x_obj, y_obj

def dist_obj(d1, a1, d2, a2):
    x1, y1 = coords(d1, a1)
    x2, y2 = coords(d2, a2)
    a = max(x1, x2) - min(x1, x2)
    b = max(y1, y2) - min(y1, y2)
    c = (a**2+b**2)**0.5
    return round(c, 3)


print(dist_obj(float(input()), int(input()), float(input()), int(input())))



