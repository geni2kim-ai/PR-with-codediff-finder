import UIKit

class LoginViewController: UIViewController {

    @IBOutlet weak var usernameField: UITextField!
    @IBOutlet weak var passwordField: UITextField!
    @IBOutlet weak var statusLabel: UILabel!
    @IBOutlet weak var loginButton: UIButton!

    override func viewDidLoad() {
        super.viewDidLoad()
        statusLabel.text = "로그인해 주세요."
    }

    @IBAction func loginTapped(_ sender: UIButton) {
        guard let username = usernameField.text, username.count >= 4 else {
            statusLabel.text = "아이디는 4자 이상 입력하세요."
            return
        }
        guard let password = passwordField.text, password.count >= 6 else {
            statusLabel.text = "비밀번호는 6자 이상 입력하세요."
            return
        }
        UserDefaults.standard.set(username, forKey: "lastUser")
        statusLabel.text = "\(username)님 환영합니다."
    }
}
