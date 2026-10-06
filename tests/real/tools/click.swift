// click X Y [button]   button: left (default) | right | double — real HID events via CGEvent (needs Accessibility)
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
default:
    post(.leftMouseDown, .left); usleep(80000); post(.leftMouseUp, .left)
}
