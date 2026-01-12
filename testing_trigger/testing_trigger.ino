/*
  ESP32 - DEBUG Trigger com identificacao de pino
  Mostra qual GPIO foi acionado
*/

struct DebugPin {
  const char* nome;
  int gpio;
};

DebugPin testPin = { "TEST_PIN", 26 };

const unsigned long PULSE_MS = 200;

void setup() {
  pinMode(testPin.gpio, OUTPUT);
  digitalWrite(testPin.gpio, LOW);

  Serial.begin(115200);
  delay(1000);

  Serial.println("=== ESP32 DEBUG TRIGGER ===");
  Serial.print("Pino configurado: ");
  Serial.print(testPin.nome);
  Serial.print(" (GPIO ");
  Serial.print(testPin.gpio);
  Serial.println(")");
  Serial.println("Envie um numero pela Serial");
}

void loop() {
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');
    msg.trim();

    if (msg.length() == 0) return;

    int value = msg.toInt();

    Serial.print("Recebido trigger: ");
    Serial.println(value);

    if (value > 0) {
      Serial.print("DISPARANDO ");
      Serial.print(testPin.nome);
      Serial.print(" no GPIO ");
      Serial.println(testPin.gpio);

      digitalWrite(testPin.gpio, HIGH);
      delay(PULSE_MS);
      digitalWrite(testPin.gpio, LOW);

      Serial.print("DESLIGADO ");
      Serial.print(testPin.nome);
      Serial.print(" no GPIO ");
      Serial.println(testPin.gpio);
    } else {
      Serial.println("Trigger invalido");
    }
  }
}
