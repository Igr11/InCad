"""What a context command acts on: the browser row the marking menu was opened on."""
_target = None


def set_target(name):
    global _target
    _target = name or None


def target():
    return _target
