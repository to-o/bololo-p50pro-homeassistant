import XCTest

/// No device credentials are used, and this test must never request an SMS.
final class BOLOLOUITests: XCTestCase {
    func testAppInstallsAndShowsLogin() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(
            app.staticTexts["BOLOLO P50 Pro"].waitForExistence(timeout: 20),
            "The native app should launch to the login screen without a saved session."
        )
        XCTAssertTrue(app.buttons["登录"].exists)
        XCTAssertTrue(app.buttons["发送验证码"].exists)
        XCTAssertTrue(app.textFields["手机号"].exists)
        XCTAssertTrue(app.buttons["从“文件”导入已有会话"].exists)
    }
}
