"""Heat-set threaded inserts for printed parts (the user: "a hole for thread inserts — a short row, small threads
mostly"). The common brass inserts (ruthex / CNC Kitchen style, pressed in with a soldering iron): the hole they go
into, the insert's length and outer diameter, and the least wall round the hole. The hole is drilled a little deeper
than the insert (DEEPER): the plastic the knurls push down goes there."""
import collections

Insert = collections.namedtuple("Insert", "name hole length outer wall")

INSERTS = (
    Insert("M2", 3.2, 4.0, 3.6, 1.3),
    Insert("M2.5", 4.0, 5.7, 4.6, 1.5),
    Insert("M3", 4.0, 5.7, 4.6, 1.6),
    Insert("M4", 5.6, 8.1, 6.3, 2.0),
    Insert("M5", 6.4, 9.5, 7.1, 2.2),
)
DEEPER = 1.0  # mm the hole runs on past the insert
DEFAULT = "M3"


def named(name):
    return next((i for i in INSERTS if i.name == name), next(i for i in INSERTS if i.name == DEFAULT))


def depth(insert):
    return insert.length + DEEPER


def boss_diameter(insert):
    """The least outer diameter of a boss that holds the insert: its outer diameter plus a wall on each side."""
    return insert.outer + 2 * insert.wall


def choices():
    return tuple((i.name, "%s (hole Ø%g × %g)" % (i.name, i.hole, depth(i))) for i in INSERTS)
