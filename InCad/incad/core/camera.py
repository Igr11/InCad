"""Camera moves for InCad's navigation on a Coin camera (pivy only, no FreeCAD): orbit about a point, pan."""
import math

from pivy import coin

ORBIT_RAD_PER_PX = 0.008


def _v(p):
    return coin.SbVec3f(float(p[0]), float(p[1]), float(p[2]))


def focal_point(cam):
    direction = cam.orientation.getValue().multVec(coin.SbVec3f(0, 0, -1))
    return cam.position.getValue() + direction * cam.focalDistance.getValue()


def orbit(cam, pivot, dx, dy, rad_per_px=ORBIT_RAD_PER_PX):
    """Inventor free orbit: dragging right/down turns the model right/down around `pivot` (a world point)."""
    rot = cam.orientation.getValue()
    up = rot.multVec(coin.SbVec3f(0, 1, 0))
    right = rot.multVec(coin.SbVec3f(1, 0, 0))
    turn = coin.SbRotation(up, -dx * rad_per_px) * coin.SbRotation(right, -dy * rad_per_px)
    p = _v(pivot)
    cam.position.setValue(p + turn.multVec(cam.position.getValue() - p))
    cam.orientation.setValue(rot * turn)


def units_per_px(cam, viewport_height_px):
    if cam.isOfType(coin.SoOrthographicCamera.getClassTypeId()):
        visible = cam.height.getValue()
    else:
        visible = 2 * cam.focalDistance.getValue() * math.tan(cam.heightAngle.getValue() / 2)
    return visible / max(1, viewport_height_px)


def pan_pixels(cam, dx, dy, viewport_height_px):
    """Dragging right/down moves the model right/down (the camera the opposite way)."""
    s = units_per_px(cam, viewport_height_px)
    rot = cam.orientation.getValue()
    right = rot.multVec(coin.SbVec3f(1, 0, 0))
    up = rot.multVec(coin.SbVec3f(0, 1, 0))
    cam.position.setValue(cam.position.getValue() - right * (dx * s) + up * (dy * s))


def frame_origin(cam, size=40.0, distance=250.0):
    """Look at the origin from the camera's current direction with about `size` model units in view
    (a new, empty part: FreeCAD's fit-all on nothing leaves the view a few mm or kilometres across)."""
    frame(cam, (0, 0, 0), size, distance)


def frame(cam, center, size, distance=250.0):
    """Look at `center` from the camera's current direction with about `size` model units in view."""
    direction = cam.orientation.getValue().multVec(coin.SbVec3f(0, 0, -1))
    if isinstance(cam, coin.SoOrthographicCamera):
        cam.height.setValue(size)
        distance = max(distance, size * 2.0)
    else:
        distance = (size / 2.0) / math.tan(cam.heightAngle.getValue() / 2.0)
    cam.position.setValue(_v(center) - direction * distance)
    cam.focalDistance.setValue(distance)
