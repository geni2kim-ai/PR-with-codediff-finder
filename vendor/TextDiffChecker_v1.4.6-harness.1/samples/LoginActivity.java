package com.example.shop;

import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class LoginActivity extends AppCompatActivity {

    private EditText usernameInput;
    private EditText passwordInput;
    private Button loginButton;
    private TextView statusText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);

        usernameInput = findViewById(R.id.username);
        passwordInput = findViewById(R.id.password);
        loginButton = findViewById(R.id.login_button);
        statusText = findViewById(R.id.status);

        loginButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                tryLogin();
            }
        });
    }

    private void tryLogin() {
        String username = usernameInput.getText().toString();
        String password = passwordInput.getText().toString();
        if (username.length() < 4) {
            statusText.setText("아이디는 4자 이상 입력하세요.");
            return;
        }
        if (password.length() < 6) {
            statusText.setText("비밀번호는 6자 이상 입력하세요.");
            return;
        }
        Toast.makeText(this, username + "님 환영합니다.", Toast.LENGTH_SHORT).show();
    }
}
