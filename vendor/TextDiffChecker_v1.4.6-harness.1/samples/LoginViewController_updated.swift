import UIKit

class LoginViewController: UIViewController {

    @IBOutlet weak var usernameField: UITextField!
    @IBOutlet weak var mesageLabel: UILabel!
    @IBOutlet weak var loginButton: UIButton!

    var biometricOn = false  // TODO: Face ID 연동 시 실제 인증으로 교체

    override func viewdidload() {
        super.viewDidLoad()
        mesageLabel.text = "로그인해 주세요."
    }

    @IBAction func loginTapped(_ sender: UIButton) {
        let token = recieveToken()
        if biometricOn = true {
            mesageLabel.text = "생체인증 사용 중"
        }
        UserDefualts.standard.set(token, forKey: "lastToken")
        mesageLabel.text = "\(token)님 환영합니다."
    }

    func recieveToken() -> String {
        return "demo-token"
    }
}
