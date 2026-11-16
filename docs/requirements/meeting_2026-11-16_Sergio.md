# Meeting 2026-11-16 — Celso Souza and Sergio Zimath, CheckOne

Summary written by the owner (Portuguese original below), recorded 2026-11-16. English points first.

## Points for the hardware

- **What it is:** a production fixture that powers and tests several units at once. Sergio developed it with
  Claude, which also proposed the name CheckOne.
- **Shared by link (claude.ai project):** the product description, the display screens (working, per Sergio), the
  interactive 3D model, the complete schematic with parts chosen by JLCPCB code, the PCB with the parts placed and
  the outline set (routing missing), the enclosure, and **a zip for Claude Code to generate the whole display
  firmware** (not in this repository's hand-over).
- **Power:** 24 V through the same DC jack as the supplies already in use. **Soft start** because production staff
  will plug the jack with the supply already on (hot plug); recommended by Claude when Sergio asked about safety
  practice for production-line equipment; it cost one extra component.
- **Monitoring:** one I²C chip monitors the power of the whole fixture. (The description and v1 say the INA226
  measures the sensor bus only, without the display and the electronics: see C-13 of the requirements.)
- **Channels:** three A/D converters; each channel supplies 24 V to the sensor and reads the 4–20 mA loop, with the
  protections it needs.
- **Display:** a ready-made I²C display module Sergio bought (he has two); from the description, the "CYD" (ESP32
  module with touch screen).
- **Board size:** Claude proposed a board 1 mm larger; Sergio measured the enclosure with a caliper and at that size
  the board would fit with no clearance at all, so he left 1 mm less on each side.

## What Sergio asked Celso for

1. Review the schematic and the whole electronics for errors.
2. Route the board.
3. Check that the board fits the enclosure and that the holes match.
4. If the routing is ready today, order the board together with the AMP.

Freedom to change whatever is needed; Sergio only wants to be told about the important changes before the version is
closed.

## Original (Portuguese)

2. Projeto CheckOne (giga de produção)

O que é: é um equipamento para a linha de produção ligar e testar vários equipamentos ao mesmo tempo. O Sergio
desenvolveu tudo com o Claude, que também sugeriu o nome "Check One".

O que já existe no projeto do Claude, compartilhado por link:
- Descrição completa do produto
- Telas do display, que segundo o Sergio já estão funcionando
- Modelo 3D interativo do equipamento, que dá para girar
- Esquemático completo, com os componentes já escolhidos pelos códigos da JLCPCB
- PCB com os componentes posicionados e o outline definido. Ainda falta o roteamento.
- Gabinete
- Um arquivo zip para o Claude Code gerar todo o firmware do display

Arquitetura eletrônica:
- Alimentação de 24 V pelo mesmo conector jack das fontes que já usamos.
- Soft start na entrada, porque na produção o pessoal vai conectar o jack com a fonte já energizada (hot plug). Foi o
  Claude que recomendou, quando o Sergio perguntou sobre normas de segurança para equipamentos de linha de produção.
  Precisou de só um componente a mais.
- Um chip I2C que monitora o consumo de potência da giga inteira.
- Três conversores A/D. Cada canal fornece 24 V para o sensor e lê a malha de 4 a 20 mA, com as proteções
  necessárias.
- Display I2C do tipo pronto que o Sergio comprou (ele tem dois). Pela descrição, parece ser o "CYD", um módulo ESP32
  com tela touch.

Dimensão da placa: o Claude sugeriu uma placa 1 mm maior. O Sergio mediu o gabinete com paquímetro e, nesse tamanho,
a placa encaixaria sem folga nenhuma. Por isso ele deixou 1 mm a menos de cada lado.

O que o Sergio pediu para você:
1. Revisar o esquemático e toda a parte eletrônica, para ver se tem algum erro.
2. Fazer o roteamento da placa.
3. Conferir se a placa cabe no gabinete e se a furação bate.
4. Se o roteamento ficar pronto hoje, pedir a placa junto com a AMP.

Você tem liberdade para mudar o que achar necessário. O Sergio só quer ser avisado das mudanças importantes antes de
fecharem a versão.
