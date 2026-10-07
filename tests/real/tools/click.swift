// click X Y [button]   button: left (default) | right | double — real HID events via CGEvent (needs Accessibility)
// click X Y drag X2 Y2   left button down at X Y, dragged in steps to X2 Y2, released there
import CoreGraphics
import Foundation
let a = CommandLine.arguments
let p = CGPoint(x: Double(a[1])!, y: Double(a[2])!)
let kind = a.count > 3 ? a[3] : "left"
let src = CGEventSource(stateID: .hidSystemState)
func post(_ t: CGEventType, _ b: CGMouseButton, clicks: Int64 = 1) {
    let e = CGEvent(mouseEventSource: src, mouseType: t, mouseCursorPosition: p, mouseButton: b)!
    e.setIntegerValueField(.mouseEventClickState, value: clicks)
    e.post(tap: .cghidEventTap)
}
CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)!.post(tap: .cghidEventTap)
usleep(200000)
switch kind {
case "right":
    post(.rightMouseDown, .right); usleep(80000); post(.rightMouseUp, .right)
case "double":
    post(.leftMouseDown, .left); usleep(60000); post(.leftMouseUp, .left); usleep(90000)
    post(.leftMouseDown, .left, clicks: 2); usleep(60000); post(.leftMouseUp, .left, clicks: 2)
case "drag":
    let q = CGPoint(x: Double(a[4])!, y: Double(a[5])!)
    post(.leftMouseDown, .left); usleep(120000)
    let steps = 12
    for i in 1...steps {
        let t = Double(i) / Double(steps)
        let m = CGPoint(x: p.x + (q.x - p.x) * t, y: p.y + (q.y - p.y) * t)
        CGEvent(mouseEventSource: src, mouseType: .leftMouseDragged, mouseCursorPosition: m, mouseButton: .left)!.post(tap: .cghidEventTap)
        usleep(25000)
    }
    usleep(120000)
    let up = CGEvent(mouseEventSource: src, mouseType: .leftMouseUp, mouseCursorPosition: q, mouseButton: .left)!
    up.setIntegerValueField(.mouseEventClickState, value: 1)
    up.post(tap: .cghidEventTap)
default:
    post(.leftMouseDown, .left); usleep(80000); post(.leftMouseUp, .left)
}
