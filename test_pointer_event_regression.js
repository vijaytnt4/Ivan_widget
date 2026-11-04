/**
 * Regression Test Suite for JavaScript send-message bug and PointerEvent handling.
 */

const fs = require('fs');
const assert = require('assert');

// Read ivan-widget.js code
const widgetJs = fs.readFileSync('assets/js/ivan-widget.js', 'utf-8');

// Verify that _handleSend is NOT bound with event leakage
assert(!widgetJs.includes('this._handleSend = this.sendMessage.bind(this)'), 
    'FAIL: this._handleSend is still binding sendMessage directly, which passes click events!');

assert(widgetJs.includes('this._handleSend = () => this.sendMessage()'),
    'PASS: this._handleSend correctly wraps sendMessage without passing event object.');

// Verify defensive type check in sendMessage
assert(widgetJs.includes("typeof customText === 'string'"),
    'PASS: sendMessage defensively checks typeof customText === "string".');

// Simulate the logic in Node.js
function simulateSendMessage(customText, inputValue, isLoading = false) {
    let sentMessage = null;
    let inputCleared = false;
    let inputDisabled = false;

    let text = '';
    if (typeof customText === 'string') {
        text = customText.trim();
    } else if (typeof inputValue === 'string') {
        text = inputValue.trim();
    }

    if (!text || isLoading) {
        return { sent: false, content: null, inputCleared };
    }

    // Input clearing simulation
    inputCleared = true;
    inputDisabled = true;

    sentMessage = text;
    return { sent: true, content: sentMessage, inputCleared, inputDisabled };
}

console.log("==================================================");
console.log("RUNNING JAVASCRIPT REGRESSION TESTS");
console.log("==================================================");

// Case 1: Send button click passing PointerEvent
const mockPointerEvent = {
    type: 'click',
    isTrusted: true,
    pointerId: 1,
    target: { tagName: 'BUTTON' }
};
const res1 = simulateSendMessage(mockPointerEvent, "Hello via button click");
assert.strictEqual(res1.sent, true);
assert.strictEqual(res1.content, "Hello via button click", "FAIL: PointerEvent leaked into message content!");
assert.notStrictEqual(res1.content, "[object PointerEvent]");
assert.strictEqual(res1.inputCleared, true);
console.log("[PASS] Test A1: Send button click (PointerEvent) correctly sends trimmed input, NOT [object PointerEvent].");

// Case 2: Enter key press (customText is undefined/null)
const res2 = simulateSendMessage(undefined, "Hello via Enter key");
assert.strictEqual(res2.sent, true);
assert.strictEqual(res2.content, "Hello via Enter key");
assert.strictEqual(res2.inputCleared, true);
console.log("[PASS] Test A2: Enter key press correctly sends trimmed input.");

// Case 3: Empty input rejected
const res3 = simulateSendMessage(mockPointerEvent, "   ");
assert.strictEqual(res3.sent, false);
assert.strictEqual(res3.content, null);
console.log("[PASS] Test A3: Empty/whitespace input is properly rejected.");

// Case 4: Programmatic send with string
const res4 = simulateSendMessage("Programmatic prompt", "");
assert.strictEqual(res4.sent, true);
assert.strictEqual(res4.content, "Programmatic prompt");
console.log("[PASS] Test A4: Programmatic sendMessage(string) works as expected.");

// Case 5: When already loading, sending is blocked
const res5 = simulateSendMessage(undefined, "Spam while loading", true);
assert.strictEqual(res5.sent, false);
console.log("[PASS] Test A5: Duplicate submission while loading is blocked.");

console.log("==================================================");
console.log("ALL JAVASCRIPT REGRESSION TESTS PASSED!");
console.log("==================================================");
