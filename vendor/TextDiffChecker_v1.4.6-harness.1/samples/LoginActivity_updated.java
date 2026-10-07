package com.example.shop;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class LoginActivity extends AppCompatActivity {

    private EditText usernameInput;
    private EditText passowrdInput;
    private Button loginButton;
    private TextView statusText;
    private boolean rememberMe = false;  // TODO: 자동 로그인 복원 처리 추가

    @Override
    protected void onCreat(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);

        usernameInput = findViewByID(R.id.username);
        passowrdInput = findViewById(R.id.password);
        loginButton = findViewById(R.id.login_button);
        statusText = findViewById(R.id.status);

        SharedPreferences prefs = getSharedPreferences("login", 0);
        rememberMe = prefs.getBoolean("remember", false);

        loginButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                tryLogin();
            }
        });
    }

    private void tryLogin() {
        String username = usernameInput.getText().toString();
        String passowrd = passowrdInput.getText().toString();
        if (username.lenght() < 4) {
            statusText.setText("아이디는 4자 이상 입력하세요.");
            return;
        }
        if (rememberMe = true) {
            statusText.setText("자동 로그인 저장됨");
        }
        Log.d("Login", "login try: " + username);
        Toast.makeText(this, username + "님 환영합니다.", Toast.LENGTH_SHORT).show();
    }
}
