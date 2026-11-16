<!-- Text extraction of CheckOne_Descricao_do_equipamento_2026-11-16.html (claude.ai artifact Xh4kmXWBBsN2iChEBn26U2, version 1794796794-94c8, read 2026-11-16), for grep. The HTML is the source. -->

# CheckOne — Descrição do equipamento

**AQTech Power Prognostics · Jiga de produção para sensores GapOne e FluxOne**

## 1. Finalidade

O CheckOne é uma jiga de bancada usada na produção para alimentar e verificar até oito sensores ao mesmo tempo. Cada saída fornece 24 V ao sensor e mede a corrente do loop de 4–20 mA que ele devolve. O equipamento converte essa corrente na grandeza física do sensor (distância em milímetros para o GapOne, fluxo magnético em militesla para o FluxOne) e mostra o resultado num display de 3,5" e numa página web servida pelo próprio equipamento.

Além das medidas dos canais, o CheckOne monitora a tensão e a corrente da alimentação dos sensores e a temperatura de dois termistores NTC: um externo, que permite acompanhar ensaios com a probe aquecida até 150 °C, e um ligado a um conector interno da caixa. Todas as grandezas são registradas com data e hora num histórico em memória, que pode ser consultado e exportado pela página web.

## 2. Sensores suportados

Cada um dos oito canais pode ser configurado, pelo display ou pela página web, para um dos tipos abaixo. A conversão é linear em toda a faixa de 4–20 mA.

| Tipo | Faixa | Unidade | Conversão |
|---|---|---|---|
| GapOne-15 | 3 a 15 | mm | 4 mA = 3 mm; 20 mA = 15 mm |
| GapOne-25 | 5 a 25 | mm | 4 mA = 5 mm; 20 mA = 25 mm |
| GapOne-50 | 10 a 50 | mm | 4 mA = 10 mm; 20 mA = 50 mm |
| FluxOne | −2000 a +2000 | mT (sem casa decimal) | B(mT) = (I_mA − 12) × 250 |
| 0–20 mA | 0 a 20 | mA | mostra a corrente do loop, sem conversão |

A condição do loop é avaliada pelos limites da NAMUR NE43 e indicada por cor na borda do cartão e na barra de cada canal: corrente abaixo de 3,6 mA indica sensor aberto ou desconectado, acima de 21 mA indica curto, e as faixas de 3,6 a 4 mA e de 20 a 21 mA indicam sinal fora da faixa nominal. No modo 0–20 mA, qualquer corrente de 0 a 21 mA é válida e só a corrente acima de 21 mA é indicada como curto. Se o loop for ligado invertido (Iin e Iout trocados), a jiga não sofre dano: o TVS da entrada conduz como diodo e segura o Iin em cerca de −0,7 V, e o BAT54S protege o conversor. O ADS1115 lê uma tensão negativa, e o canal mostra "4–20 mA invertido" piscando no lugar da medida. As telas não exibem texto de status. A saída de 24 V de todos os canais fica sempre ligada.

## 3. Características principais

| Item | Especificação |
|---|---|
| Canais | 8 saídas de 24 V com medição de 4–20 mA |
| Alimentação | Fonte externa de 24 V CC, tipo CFTV, 2 A ou mais, plugue 5,5 × 2,1 mm |
| Proteção por canal | Fusível rearmável de 200 mA (disparo em 500 mA) |
| Medição dos loops | Shunt de 120 Ω 0,1 %, conversor de 16 bits, resolução de ~1 µA |
| Monitoração da alimentação | Tensão e corrente do barramento de 24 V dos sensores |
| Temperatura | 2 termistores NTC 100 kΩ / B3950 (externo até 150 °C e interno) |
| Relógio | RTC com bateria CR2032, horário de Brasília, acerto por NTP ou pela página web |
| Registro | 1 amostra a cada 5 s, até 48 h de histórico |
| Display | 3,5", 480 × 320 px, toque resistivo, interface em retrato |
| Conectividade | Wi-Fi: ponto de acesso próprio ou rede da fábrica |
| Gabinete | AK-P-08A, ABS, 145 × 90 × 38,8 mm, fixação em trilho DIN |

## 4. Interface com o operador

### 4.1 Display

O display é um módulo CYD ESP32-3248S035R, com tela de 3,5" (controlador ST7796) e toque resistivo (XPT2046), operado com a caneta que acompanha o módulo. A interface é desenhada em retrato, 320 × 480 px, e o equipamento é usado girado 90° na bancada. Nessa posição, a coluna da esquerda da tela mostra os canais CH1–CH4, que ficam na lateral esquerda do gabinete, e a coluna da direita mostra CH5–CH8, na lateral direita. Cada canal aparece na tela do mesmo lado do seu borne.

O cabeçalho de todas as telas principais mostra a data e a hora, a tensão e a corrente de 24 V e as temperaturas dos dois NTC (T1 e T2). O equipamento tem cinco telas:

- **Visão geral:** um cartão por canal, com o tipo de sensor, a medida, a corrente do loop e uma barra com a posição na faixa de 4–20 mA. Tocar num cartão abre o detalhe daquele canal.
- **Lista:** os oito canais em dois blocos (CH1–4 e CH5–8), com medida, corrente e barra em cada linha.
- **Detalhe do canal:** a medida em destaque, a corrente, a barra com escala dupla (mA e unidade de engenharia), mínimo, máximo, média, ruído pico a pico e a tendência dos últimos 60 s. Botões levam ao canal anterior ou ao seguinte e zeram o mínimo e o máximo.
- **Configuração:** seleção do tipo de sensor de cada canal (GapOne-15, -25, -50, FluxOne ou 0–20 mA), com opção de aplicar o mesmo tipo a todos e de salvar a configuração, e acesso à tela de calibração. A tela mostra também a rede em uso (modo, nome da rede, IP e endereço checkone.local) e tem o botão "Restaurar rede", que, após confirmação, apaga a rede salva, volta ao ponto de acesso CheckOne e restaura a senha de configuração padrão, mantendo os tipos de sensor.
- **Calibração:** zero de todos os canais com um toque e ajuste do ganho com 20,00 mA injetados, com a situação de cada canal (seção 5.7).

### 4.2 Página web

O CheckOne serve uma página no padrão visual da AQTech, acessível pelo navegador de um computador ou celular conectado ao Wi-Fi da jiga. A página é um arquivo único, sem dependências externas, e funciona mesmo sem acesso à internet. Ela tem três seções:

- **Painel:** os oito canais em tempo real, com a mesma informação do display, mais a tensão e a corrente de 24 V, a temperatura, a data e a hora e o tempo de histórico disponível.
- **Histórico:** gráfico dos canais escolhidos, em mA ou na unidade da medida, com janelas de 15 min, 1 h ou todo o buffer; gráficos da corrente de 24 V e da temperatura; exportação em CSV.
- **Configuração:** nome do equipamento (CheckOne1 a CheckOne5), tipo de sensor por canal, acerto do relógio com a hora do computador e rede Wi-Fi (ponto de acesso próprio ou rede da fábrica). A configuração não pede senha, e as alterações valem também para o display.

O acesso pela rede foi pensado para que a jiga nunca fique inacessível e para que várias jigas convivam na mesma rede. Cada jiga recebe um nome de CheckOne1 a CheckOne5, escolhido no display (botão "Nome" da tela de Configuração) ou na página web. O nome aparece no cabeçalho das telas, é o nome do ponto de acesso Wi-Fi próprio (aberto, sem senha) e forma o endereço da página na rede da fábrica (checkone1.local a checkone5.local, por mDNS). Quando configurada para a rede da fábrica, a jiga mantém o ponto de acesso ativo ao mesmo tempo (modo AP + STA); se não conseguir entrar na rede em cerca de 30 s, continua acessível pelo ponto de acesso. O botão "Restaurar" do display apaga a rede salva e volta ao ponto de acesso, mantendo o nome e os tipos de sensor.

## 5. Arquitetura eletrônica

### 5.1 Alimentação

A entrada de 24 V passa, nessa ordem, por um fusível rearmável de 1,6 A, por um supressor de transientes SMBJ24A (grampeamento em 38,9 V) e por um diodo Schottky SS34 de proteção contra inversão de polaridade. Um LED verde indica a presença dos 24 V depois dessa proteção. A fonte precisa ser de 24 V ±5% (no máximo 25,2 V): acima disso o TVS começa a conduzir.

Logo depois vem um circuito de partida suave com um P-MOSFET AO4485 (40 V, 13 mΩ, SOP-8), que combina um atraso e uma rampa. O gate é polarizado por um divisor de 4,7 kΩ (gate-source) e 10 kΩ (gate-terra), que limita a tensão gate-source a cerca de −7,7 V com 24 V e −12,4 V no grampeamento do TVS, dentro dos ±20 V do MOSFET, sem precisar de zener. Um eletrolítico de 220 µF entre gate e source (positivo no source) mantém o gate junto do source no instante em que o plugue encaixa: pelo divisor capacitivo com os 2 µF entre gate e dreno, a tensão gate-source inicial fica em ~−0,2 V, e o MOSFET permanece desligado enquanto os contatos do conector se estabilizam. Esse capacitor carrega pelos resistores e, depois de ~0,2 s, o MOSFET começa a conduzir. Dois capacitores de 1 µF entre gate e dreno, em série com um resistor de 1 kΩ, controlam então a subida da tensão: a alimentação chega a 24 V em ~20 ms, e o pico de corrente para carregar os ~1,3 mF da placa e dos sensores fica entre ~1 e 1,8 A. Assim, no encaixe não passa corrente pelos contatos, e o faiscamento no conector desaparece. O resistor de 1 kΩ em série com os capacitores gate-dreno é essencial: sem ele, a subida rápida da tensão no encaixe (~2 µs, pela oscilação do cabo da fonte) seria acoplada ao gate pelos capacitores gate-dreno, e o MOSFET conduziria um pulso de ~10 A logo no contato. A simulação do circuito completo no ngspice confirmou o comportamento: no encaixe com a fonte ligada, a tensão gate-source fica em ~0 V, o pico no conector é de ~5,8 A por poucos microssegundos (carga do cerâmico de entrada, com o TVS grampeando a oscilação do cabo em ~31,5 V), o MOSFET começa a conduzir depois de ~0,2 s, a corrente de partida fica em 1,34 A e o barramento chega a 22 V em ~0,27 s. Num surto de 10/1000 µs de 300 V com 4 Ω, com uma fonte de apenas 100 µF na saída, o TVS conduz 5,2 A (o limite dele é 15,4 A), a entrada fica abaixo de 31,5 V e o barramento dos sensores não passa de 28,8 V. A energia dissipada no MOSFET a cada partida (~0,4 J) é absorvida com folga pelo encapsulamento SOP-8. Em funcionamento, a perda no MOSFET é desprezível (~10 mW). Depois de desligar, os capacitores do gate descarregam em ~1 s. O SS34 continua responsável pela proteção contra inversão, porque o diodo interno de um P-MOSFET de partida suave fica no sentido que não protege. Os eletrolíticos do filtro ficam todos depois do MOSFET; só o cerâmico de 100 nF da entrada fica antes dele.

Em seguida vem um filtro π LC contra o ruído da fonte: 220 µF + 1 µF + 100 nF, indutor de 68 µH (FCH1040-680M) e mais 220 µF + 1 µF + 100 nF. A frequência de corte fica em torno de 41 Hz, o que atenua a ondulação de chaveamento da fonte e impede que o chaveamento do regulador de 5 V volte para a linha dos sensores. A queda no indutor é de ~0,16 V com a jiga carregada.

A partir daí, a alimentação se divide em dois ramos. O primeiro alimenta um regulador chaveado XL1509-5.0, que gera os 5 V (até 2 A), sinalizados por um LED verde. O 5 V chega ao display através de uma posição para diodo SS34 (proteção contra retorno quando o USB do módulo é ligado junto) ou resistor de 0 Ω, e de dois ferrite beads GZ2012D601TF em paralelo (600 Ω a 100 MHz, 500 mA cada), que bloqueiam o ruído de alta frequência.

Os 3,3 V da jiga são gerados na própria placa por um regulador linear XC6206P332MR (200 mA, corrente de repouso de ~1 µA), alimentado pelo 5 V, com capacitores cerâmicos de 1 µF na entrada e na saída. Os pinos de 3,3 V dos conectores dos displays ficam sem ligação: a medição não depende mais do regulador do display, e os chips da jiga não recebem alimentação indevida pelas entradas quando o display está desconectado. Os pull-ups do I²C e o RTC ficam ligados direto à saída do regulador; os ADS1115, o INA226 e os divisores dos NTC passam por um filtro RC (10 Ω e 1 µF) e formam o 3,3 V analógico (3V3A). Um terceiro LED verde indica a presença dos 3,3 V da jiga. Um quarto LED verde ("3V3D") indica o 3,3 V do display: ele é alimentado, por um resistor de 1 kΩ, pelos pinos de 3,3 V dos conectores J_I2C_CYD e J_I2C_JC, que não alimentam mais nada na jiga. O display de 4,3", ligado pelo J_EXT, não acende esse LED, porque o J_EXT não tem pino de 3,3 V.

O segundo ramo é o barramento de 24 V dos sensores. Ele passa pelo shunt de 50 mΩ (dois resistores de 100 mΩ em paralelo) do monitor INA226, que mede apenas a corrente consumida pelos sensores, sem a influência do display e da eletrônica de medição. Em seguida, cada uma das oito saídas tem o seu próprio fusível rearmável de 200 mA, de modo que um curto num cabo ou num sensor desliga só aquele canal. Depois do fusível, cada saída tem um ferrite bead GZ2012D601TF em série e um capacitor de 100 nF para o terra junto ao borne. Esse filtro LC por canal impede que o ruído de chaveamento de um sensor passe para os outros pelo barramento comum e desvia para o terra a interferência captada pelos cabos.

### 5.2 Medição dos loops de 4–20 mA

As saídas de corrente dos sensores são isoladas. A corrente entra na jiga pelo pino Iin, passa pelo shunt de 120 Ω 0,1 % para o terra e retorna ao sensor pelo pino Iout, ligado ao terra da jiga. A tensão no shunt (2,4 V a 20 mA) é lida em modo single-ended por dois conversores ADS1115 de 16 bits, quatro canais cada, com fundo de escala de ±4,096 V e 128 amostras por segundo. Esse arranjo cobre com folga a faixa de falha acima de 21 mA, mantendo a tensão abaixo da alimentação do conversor.

Cada entrada tem um TVS SMAJ5.0A do Iin para o terra, um resistor série de 1 kΩ, um diodo duplo BAT54S de grampeamento para 3,3 V e para o terra e um capacitor de 10 nF. O TVS protege o shunt num erro de fiação com o +24 ligado ao Iin: ele grampeia a tensão em ~6,4 V e a corrente alta faz desarmar o fusível de 200 mA da saída do próprio canal em fração de segundo. Esse conjunto protege o conversor contra descargas eletrostáticas e contra contato acidental com os 24 V, e forma um filtro passa-baixa de ~16 kHz contra o ruído de chaveamento.

### 5.3 Temperatura

A jiga tem duas entradas de NTC (100 kΩ a 25 °C, B = 3950, conector XH): NTC1, na janela frontal, para a probe com cabo de 1,35 m, e NTC2, num conector interno da caixa. Cada termistor forma um divisor com um resistor de 10 kΩ, dimensionado para a faixa de até 150 °C, com a mesma proteção das entradas de corrente (1 kΩ, BAT54S e 10 nF) e mais um capacitor de 1 µF em paralelo com o NTC, junto ao conector. Esse capacitor forma, com a impedância do divisor (~9 kΩ a 25 °C), um filtro de ~17 Hz contra o ruído captado pelo cabo do termistor, inclusive o de 60 Hz da rede. A constante de tempo (~10 ms) é muito menor que o tempo de resposta do próprio termistor, de alguns segundos, então a medida não é afetada. As tensões dos dois divisores (AIN0 e AIN2) e a tensão de 3,3 V que os alimenta (AIN1) são lidas por um terceiro ADS1115, o que torna a medida ratiométrica e independente da tolerância do regulador. A conversão usa a equação Beta. Para validar probes a 140 °C, recomenda-se calibrar em dois ou três pontos e usar a equação de Steinhart-Hart com os coeficientes ajustados.

### 5.4 Relógio

Um RTC PCF8563 com cristal de 32,768 kHz mantém a data e a hora. Com o equipamento desligado, ele é alimentado por uma bateria CR2032, selecionada automaticamente por dois diodos BAT54W. O relógio trabalha no horário de Brasília (UTC−3, sem horário de verão) e é acertado por NTP quando a jiga está numa rede com internet (servidores pool.ntp.br), ou pela página web, com a hora do computador.

### 5.5 Barramento I²C

Todos os periféricos de medição compartilham um barramento I²C a 400 kHz, ligado ao conector CN1 do CYD (GPIO21 = SDA, GPIO22 = SCL), com pull-ups de 4,7 kΩ. As leituras são feitas por varredura, sem uso de linhas de interrupção.

| Endereço | Componente | Função |
|---|---|---|
| 0x40 | INA226 | Tensão e corrente do barramento de 24 V dos sensores |
| 0x48 | ADS1115 U1 | Canais CH1–CH4 |
| 0x49 | ADS1115 U2 | Canais CH5–CH8 |
| 0x4A | ADS1115 U3 | NTC1 (AIN0), referência de 3,3 V (AIN1), NTC2 (AIN2) |
| 0x51 | PCF8563 | Relógio de tempo real |

### 5.6 Processamento e firmware

O processamento é feito pelo ESP32 do módulo CYD (4 MB de flash, sem PSRAM). O firmware é desenvolvido em ESP-IDF v5.5 com a biblioteca gráfica LVGL. A página web é embutida no firmware, compactada, e servida pelo servidor HTTP do ESP-IDF. Todas as configurações (tipo de sensor de cada canal, rede Wi-Fi, senha de configuração, calibração das entradas e dos NTC) são gravadas na flash do ESP32, na partição NVS, e mantidas após desligar o equipamento. A gravação acontece apenas quando o operador salva uma alteração, o que preserva a vida útil da flash. O histórico de medidas, por outro lado, fica só na RAM (seção 6).

Para robustez, o firmware inclui: watchdog de tarefas, detecção de queda de tensão, recuperação automática do barramento I²C travado, detecção de ADS1115 ou INA226 ausentes ou sem resposta (com aviso na tela) e atualização de firmware pela página web (OTA), com duas partições de aplicação.

### 5.7 Calibração das entradas de corrente

A tela de calibração (acessada pela Configuração) ajusta o zero e o ganho de cada canal. Os resultados são gravados na flash e aplicados a todas as leituras: I = (leitura − offset) × ganho.

1. **Zero:** com todos os sensores desconectados (entradas em 0 mA), o operador toca em "Calibrar zero". O firmware faz a média de cerca de 2 s de leituras em cada canal e grava esse valor como offset dos 8 canais de uma vez.
2. **Ganho:** o operador injeta 20,00 mA no Iin e toca em "Calibrar 20 mA". O firmware calibra todos os canais que estiverem medindo entre 18 e 22 mA, com ganho = 20,000 / (leitura − offset), e marca cada um como calibrado. Como os oito shunts vão para o terra, uma única fonte não pode ser ligada em série pelos oito canais: com uma fonte, ela é passada de canal em canal e o botão é tocado em cada um; com várias fontes, os canais são calibrados de uma vez.
3. **Salvar** grava os coeficientes; **Restaurar padrão** volta para offset 0 e ganho 1,0000.

Recomenda-se usar um calibrador de corrente com exatidão de 0,05 % ou melhor e repetir a calibração periodicamente.

## 6. Registro de dados

O CheckOne grava uma amostra a cada 5 segundos, com a média das leituras do intervalo. Cada registro ocupa cerca de 28 bytes: hora, as oito correntes, a tensão e a corrente de 24 V e as duas temperaturas. O histórico guarda até 48 horas (34 560 registros, ~1 MB). No JC3248W535 e no JC4880P443C, o buffer circular fica na PSRAM. No CYD, que não tem PSRAM, o histórico fica numa partição própria da flash, gravada em páginas pequenas a cada ~1 minuto (os setores de 4 KB são apagados à medida que o anel avança); com o anel de 48 h, cada setor é regravado uma vez a cada dois dias, muito abaixo do limite de regravações da flash. Num desligamento abrupto perde-se no máximo o último minuto. Na flash, o histórico também sobrevive a um desligamento. Quando cheio, os registros mais antigos são substituídos, e a exportação em CSV da página web baixa o histórico completo.

## 7. Mecânica e conexões

### 7.1 Gabinete e montagem

O equipamento é montado no gabinete AK-P-08A, de ABS, com 145 × 90 × 38,8 mm e fixação em trilho DIN. A placa principal mede 122 × 87 mm e é fixada pelos quatro furos a 115 × 80 mm, alinhados com os parafusos da tampa. O CYD é parafusado sobre a placa principal com espaçadores M3 de ~21 mm, com a tela rente à tampa, através de um recorte de 86 × 56 mm no rebaixo de 101 × 68 mm.

Os componentes mais altos (regulador, indutor e capacitores eletrolíticos) ficam numa das pontas da placa, fora da área do display. O RTC e a bateria ficam na outra ponta, longe do regulador chaveado.

### 7.2 Disposição dos conectores

As duas laterais longas do gabinete têm janelas de 100 mm para os conectores. Na posição de uso, com o equipamento girado 90°:

- **Lateral esquerda:** saídas CH1–CH4 e entrada de 24 V.
- **Lateral direita:** saídas CH5–CH8, conector NTC1 e LEDs verdes de 24 V, 5 V, 3,3 V da jiga e 3,3 V do display, visíveis de cima.
- **Interno:** conector NTC2, na ponta esquerda da placa.

Cada borne fechado de 4 vias tem 21,92 mm de comprimento. A lateral esquerda ocupa 96,7 mm e a direita cerca de 97 mm, dos 100 mm de cada janela.

### 7.3 Conectores das saídas

Cada saída usa um borne plugável de 4 vias, passo de 5,08 mm, com corpo fechado nas laterais (KF2EDGRC-5.08-4P), e o plugue de parafuso correspondente no cabo (KF2EDGK-5.08-4P). A pinagem é a mesma nos oito canais, de modo que qualquer cabo de teste serve em qualquer saída.

| Pino | Serigrafia | Função |
|---|---|---|
| 1 | +24 | Alimentação de 24 V do sensor (após o fusível do canal) |
| 2 | GND | Retorno da alimentação |
| 3 | Iin | Entrada da corrente do loop (para o shunt) |
| 4 | Iout | Retorno do loop para o sensor (ligado ao terra da jiga) |

### 7.4 Conexões internas com o display

A placa principal liga-se ao display por cabos de 1,25 mm e 4 vias (padrão MX1.25, compatível com PicoBlade), montados em conectores SMD verticais.

| Conector | Destino no CYD | Sinais |
|---|---|---|
| J_PWR | P1 do CYD ou do JC3248W535 | 5 V, TX, RX, GND (TX e RX sem ligação) |
| J_I2C_CYD | CN1 do CYD | GND, GPIO22 (SCL), GPIO21 (SDA), 3,3 V só para o LED 3V3D |
| J_I2C_JC | P4 do JC3248W535 (JST 1,25 mm) | GND, 3,3 V só para o LED 3V3D, IO17 (SDA), IO18 (SCL) |
| J_EXT (barra de pinos 1 × 4, 2,54 mm) | Conector de 26 pinos do JC4880P443C, por cabo externo | 5V, GND, SDA, SCL |

### 7.5 Displays suportados

A placa aceita três módulos de display, um de cada vez. Os dois de 3,5" (320 × 480) ficam dentro da caixa e usam o mesmo conjunto de telas. O de 4,3" (480 × 800) fica fora da caixa, ligado por cabo, e tem um conjunto de telas próprio, com o mesmo conteúdo em escala 1,5×.

|  | CYD ESP32-3248S035R | Guition JC3248W535 | Guition JC4880P443C |
|---|---|---|---|
| Montagem | Dentro da caixa | Dentro da caixa | Fora da caixa, por cabo |
| Processador | ESP32, 4 MB de flash, sem PSRAM | ESP32-S3, 16 MB de flash, 8 MB de PSRAM | ESP32-P4 + ESP32-C6 (Wi-Fi), 16 MB de flash, 32 MB de PSRAM |
| Tela | 3,5", 320 × 480, ST7796, SPI | 3,5", 320 × 480, AXS15231B, QSPI | 4,3", 480 × 800, ST7701S, MIPI-DSI |
| Toque | Resistivo (XPT2046), com caneta | Capacitivo (I²C interno, GPIO4/8) | Capacitivo (GT911, I²C GPIO7/8) |
| Alimentação | P1: 5V, TX, RX, GND | P1: 5V, TX, RX, GND (mesma pinagem) | Pinos de 5 V e GND do conector de 26 pinos |
| I²C da jiga | CN1: GND, IO22, IO21, 3V3 | P4: GND, 3V3, IO17, IO18 | Pinos de I²C do conector de 26 pinos (barramento GPIO7/8, compartilhado com o toque) |
| Conector na jiga | J_PWR + J_I2C_CYD | J_PWR + J_I2C_JC | J_EXT |
| Tamanho do módulo | ~93 × 55 mm (a confirmar) | 94,5 × 62,0 mm | 114,4 × 66,8 mm |

O J_PWR serve aos dois. Cada display tem o seu conector de I²C, ligados em paralelo ao mesmo barramento da jiga. Os pinos de 3,3 V dos dois conectores só alimentam o LED 3V3D (e ficam ligados entre si nesse ponto), e os dois displays seriam mestres no mesmo barramento I²C, então **conecte só um display de cada vez**. O JC3248W535 tem proteção própria na entrada de 5 V (MOSFET e TVS de 6 V) e gera os 3,3 V com um conversor chaveado, então tolera bem a queda no diodo SS34. O CYD gera os 3,3 V com um regulador linear que precisa de ~4,4 V na entrada; com o SS34 e os beads, o CYD recebe ~4,5 V (4,3 V no pior caso de tolerância do XL1509). Por isso a posição do SS34 aceita um resistor de 0 Ω: com o CYD, monte o 0 Ω e não ligue o USB do display com a jiga energizada. O firmware tem uma versão para cada módulo, com os pinos de I²C, o driver de tela e o de toque correspondentes. O JC3248W535 tem vidro frontal de 94,5 × 62,0 mm e furos de fixação diferentes, então pede uma tampa com recorte próprio e outra posição de espaçadores.

**Display externo de 4,3" (JC4880P443C).** O módulo não cabe na caixa (66,8 mm de largura contra ~66 mm entre as janelas) e fica fora dela, ligado à jiga por um cabo de 4 vias que sai pela ponta esquerda da caixa, sem prensa-cabo. Na jiga, o cabo encaixa no J_EXT, uma barra de pinos 1 × 4 de 2,54 mm (PZ254V-11-04P, PTH: 5V, GND, SDA, SCL). No display, as quatro vias vão aos pinos de 5 V, GND, SDA e SCL do conector de 26 pinos (2,54 mm). O cabo pode ter conectores fêmea de 2,54 mm (tipo Dupont) nas duas pontas. O consumo do módulo, de algumas centenas de mA, cabe nos 3 A por pino da barra e nos dois beads do 5 V.

Com um cabo de 10 cm, a capacitância que ele acrescenta ao I²C é desprezível: o barramento funciona a 400 kHz, como nos displays de 3,5", com os mesmos pull-ups de 4,7 kΩ da placa, e não precisa de fios trançados. Os endereços da jiga (0x40, 0x48–0x4A, 0x51) não conflitam com o toque GT911 (0x5D ou 0x14) nem com o codec de áudio (0x18), que estão no mesmo barramento do display.

O firmware do JC4880P443C é uma terceira versão: ESP32-P4 com Wi-Fi pelo ESP32-C6 (ESP-Hosted), tela por MIPI-DSI e interface em 480 × 800. A placa usa um ESP32-P4 em amostra de engenharia (revisão v1.3), que exige uma configuração específica das ferramentas de compilação.

### 7.6 Serigrafia

Todos os conectores têm identificação e marca do pino 1 na serigrafia da placa.

| Conector | Serigrafia |
|---|---|
| Bornes CH1–CH8 | "CH1" … "CH8" e, sob cada pino, "+24", "GND", "Iin", "Iout" |
| Entrada DC | "24V DC" e "(+) centro" |
| Conectores dos NTC | "NTC1" e "NTC2" |
| Ilhas de teste (verso) | "24V", "5V", "3V3", "3V3A", "SDA", "SCL", "GND" |
| LEDs | "24V", "5V", "3V3" e "3V3D" |
| J_PWR | "DISPLAY 5V" e "5V TX RX GND" |
| J_I2C_CYD | "I2C CYD" e "GND SCL SDA 3V3" |
| J_I2C_JC | "I2C JC3248" e "GND 3V3 SDA SCL" |
| J_EXT | "DISPLAY EXT" e "5V GND SDA SCL" |
| Bateria | "CR2032" e "+" do lado da torre do contato positivo |
| Placa | "CheckOne · AQTech" |

### 7.7 Ilhas de teste

O verso da placa tem ilhas SMD de Ø1,8 mm, sem componente, para medição na bancada: 24V, 5V, 3V3, 3V3A (analógico, depois do filtro RC), SDA, SCL e duas de GND.

## 8. Lista de componentes

A JLCPCB monta apenas os componentes SMD (seção 8.1). Os componentes PTH (bornes, entrada DC, conectores dos NTC e suporte da bateria) são comprados à parte na LCSC e soldados à mão, junto com os demais itens avulsos (seção 8.2). Peças compradas no estoque da JLCPCB não são enviadas soltas, por isso os itens avulsos vêm da LCSC.

### 8.1 Componentes SMD (montados pela JLCPCB)

| Função | Componente | Código JLCPCB | Qtd | Classe |
|---|---|---|---|---|
| Conversores dos loops e dos NTC | ADS1115IDGSR | C37593 | 3 | Extended |
| Monitor de 24 V | INA226AIDGSR | C49851 | 1 | Extended |
| RTC | PCF8563T/5,518 | C7440 | 1 | Basic |
| Cristal do RTC (32,768 kHz, 12,5 pF) | Q13FC13500004 | C32346 | 1 | Basic |
| Regulador 24 → 5 V | XL1509-5.0E1 | C61063 | 1 | Basic |
| Indutor do regulador e do filtro de entrada (68 µH) | FCH1040-680M | C20415548 | 2 | Extended |
| Eletrolítico 220 µF / 50 V (filtro de entrada, buck, barramento e atraso da partida suave) | JVJ50V220M10x10 | C46550417 | 6 | Extended |
| Cerâmico 1 µF / 50 V (filtro de entrada, buck, LDO, RC do 3,3 V, rampa da partida suave e NTC) | CL21B105KBFNNNE | C28323 | 10 | Basic |
| Regulador 5 → 3,3 V (200 mA) | XC6206P332MR | C5446 | 1 | Basic |
| Cerâmico 10 nF / 50 V (filtro das entradas) | 0603B103K500NT | C57112 | 10 | Basic |
| Cerâmico 100 nF / 50 V (desacoplamento, filtro de entrada e saídas) | CC0603KRX7R9BB104 | C14663 | 16 | Basic |
| Cerâmico 22 pF C0G (oscilador do RTC) | CL10C220JB8NNNC | C1653 | 1 | Basic |
| Shunt de 24 V (2 × 100 mΩ em paralelo = 50 mΩ, 1206) | 1206W4F100LT5E (Uniroyal) | C25334 | 2 | Basic |
| Shunts dos loops (120 Ω 0,1 %, 1206) | RT1206BRD07120RL | C870389 | 8 | Extended |
| Resistor 10 kΩ (NTC1, NTC2, LED de 24 V e gate da partida suave) | 0603WAF1002T5E | C25804 | 4 | Basic |
| Resistor 1,5 kΩ (LED de 5 V) | 0603WAF1501T5E | C22843 | 1 | Basic |
| Resistor 1 kΩ (série das entradas, LEDs de 3,3 V e gate-dreno da partida suave) | 0603WAF1001T5E | C21190 | 13 | Basic |
| Resistor 0 Ω (alternativa ao SS34 do 5 V do display) | 0603WAF0000T5E | C21189 | 1 | Basic |
| Resistor 10 Ω (filtro RC do 3,3 V) | 0603WAF100JT5E | C22859 | 1 | Basic |
| Ferrite bead 600 Ω, 500 mA (5 V do display e saídas de 24 V) | GZ2012D601TF | C1017 | 10 | Basic |
| Resistor 4,7 kΩ (pull-up I²C e gate da partida suave) | 0603WAF4701T5E | C23162 | 3 | Basic |
| Fusível rearmável da entrada (1,6 A) | 1812L160/30GR | C18198337 | 1 | Extended |
| Fusíveis rearmáveis das saídas (200 mA) | JK-SMD0805-020-30V | C516070 | 8 | Extended |
| Supressor de transientes | SMBJ24A (hongjiacheng) | C19077578 | 1 | Basic |
| Chave de partida suave (P-MOSFET 40 V) | AO4485 (ElecSuper ou UMW) | C5334068 ou C5125949 | 1 | Extended |
| Diodo Schottky (inversão, buck, 5 V do display) | SS34 (MDD) | C8678 | 3 | Basic |
| Clamp das entradas | BAT54S (hongjiacheng) | C7420333 | 10 | Basic |
| TVS das entradas Iin | SMAJ5.0A (Liown) | C2925443 | 8 | Basic |
| Seleção 3,3 V / bateria do RTC | BAT54W (hongjiacheng) | C7502705 | 2 | Basic |
| LEDs 24 V, 5 V, 3,3 V da jiga e 3,3 V do display (verdes) | KT-0805G | C2297 | 4 | Basic |
| Conectores dos displays (MX1.25, vertical) | 1.25-4P LT (SHOU HAN) | C668611 | 3 | Extended |

### 8.2 Compra avulsa e montagem manual

**Componentes PTH, soldados à mão na placa**

| Função | Componente | Código LCSC | Qtd |
|---|---|---|---|
| Bornes das saídas (fechados, 5,08 mm) | KF2EDGRC-5.08-4P (Kefa) | C441238 | 8 |
| Entrada de alimentação (5,5 × 2,1 mm) | DC-005-A200 (XUNPU) | C720557 | 1 |
| Conectores NTC1 e NTC2 (XH, vertical) | B2B-XH-A(LF)(SN) (JST) | C158012 | 2 |
| Conector do display externo (barra de pinos 1 × 4, 2,54 mm) | PZ254V-11-04P (XFCN) | C2691448 | 1 |
| Suporte da bateria CR2032 | BS-02-A1AJ006 (MYOUNG) | C964745 | 1 |

**Itens avulsos, não soldados na placa**

| Item | Componente | Código | Qtd |
|---|---|---|---|
| Plugues dos cabos dos sensores | KF2EDGK-5.08-4P (Kefa) | C440882 | 8 |
| Bateria | CR2032 | — | 1 |
| Termistores | NTC 100 kΩ B3950 com plugue XH | — | 2 |
| Cabos do display | 1,25 mm (MX1.25), 4 vias, "mesmo lado" | — | 2 |
| Display | CYD ESP32-3248S035R, Guition JC3248W535 ou Guition JC4880P443C | — | 1 |
| Cabo do display externo (só JC4880P443C) | 4 vias, 10 cm, conectores fêmea de 2,54 mm (tipo Dupont) nas duas pontas | — | 1 |
| Gabinete | AK-P-08A | — | 1 |
| Fonte | 24 V CC, 2 A ou mais, plugue 5,5 × 2,1 mm | — | 1 |

## 9. Verificação por simulação

O circuito de potência e das entradas foi simulado no ngspice, da entrada de 24 V até os 8 sensores, com parâmetros de pior caso dos datasheets (por exemplo, limiar de gate do AO4485 de −1,0 V e ruptura do SMBJ24A de 26,7 V) e o canal 1 com o loop de corrente completo (shunt, TVS, 1 kΩ, BAT54S, 10 nF e entrada do ADS1115). Os netlists, os resultados e os gráficos estão em `docs/simulacao/` no pacote do projeto.

| Situação | Resultado | Avaliação |
|---|---|---|
| Fonte ligada na tomada com o plugue encaixado | Pico de 1,30 A; barramento em 22 V em ~0,17 s | OK |
| Plugue encaixado com a fonte ligada | MOSFET não conduz no contato (Vgs 0,1 V); pico de 5,8 A por ~3 µs no cerâmico de entrada; TVS grampeia em ~30 V | OK, sem faiscamento relevante |
| Surto de 10/1000 µs, 300 V / 4 Ω, fonte com 100 µF | TVS com 6,2 A (limite 15,4 A); barramento ≤ 28,7 V; leitura do ADS inalterada | OK |
| Sensor encaixado com a jiga ligada | Pico de 12 A por ~0,1 ms no canal; barramento cai para 22,4 V; outros canais não percebem | OK, PTC não desarma |
| Curto na saída de um canal | ~10 A até o PTC do canal desarmar; barramento cai para 18 V nesse intervalo | OK, com ressalva (abaixo) |
| +24 V ligado no Iin | TVS do Iin grampeia em ~7,4 V; pino do ADS limitado a 3,6 V pelo BAT54S; PTC do canal desarma | OK, com ressalva (abaixo) |
| Loop invertido (20 mA) | Iin em −0,84 V; pino do ADS em −0,24 V (limite −0,3 V) | OK; firmware detecta pela leitura negativa |
| Fonte com polaridade invertida | TVS conduz direto, SS34 bloqueia; nada da jiga recebe tensão negativa | OK |
| Fonte desconectada com a jiga ligada | Sensores perdem alimentação em ~15 ms; buck desliga em ~46 ms | OK, com ressalva (abaixo) |
| Fonte em 28 V | TVS conduz ~1 A continuamente (~30 W) | Não admissível: fonte limitada a 25,2 V |

**Ressalvas e decisões resultantes:**

- **Tensão da fonte:** o SMBJ24A começa a conduzir a partir de 26,7 V. A fonte precisa ser de 24 V ±5% (no máximo 25,2 V). Fontes de CFTV com trimpot de ajuste não devem ser reguladas acima disso; vale conferir a tensão de cada fonte antes do uso.
- **Curto com fonte de 2 A:** com uma fonte real, o limite de corrente dela (~2–2,5 A) atua antes do PTC do canal, e o barramento cai enquanto o PTC não desarma (de frações de segundo a ~1 s). Durante esse tempo os outros sensores e o display podem reiniciar; depois do desarme, a jiga volta sozinha.
- **+24 V no Iin com fonte de 2 A:** pelo mesmo motivo, a corrente no TVS do Iin fica em ~2 A (~13 W) até o PTC do canal desarmar, o que pode levar ~1 s. É o limite do que um TVS em SMA suporta; se esse erro de fiação for frequente, trocar o SMAJ5.0A pelo SMBJ5.0A (encapsulamento SMB, 600 W) dá mais margem.
- **Desligamento abrupto:** a jiga tem ~46 ms de energia depois que a fonte é retirada. Isso não basta para gravar um bloco de 4 KB na flash. O firmware deve gravar o histórico do CYD em páginas pequenas e frequentes (por exemplo, a cada minuto), para perder no máximo o último minuto num desligamento.
- **Partida:** nos primeiros ~0,5 s, os sensores ainda estão alimentando; o firmware ignora as leituras dos canais por 2 a 3 s depois de ligar e enquanto a tensão do barramento estiver abaixo de 20 V.

## 10. Comparação com a prática da indústria

As soluções comerciais e as recomendações de bancada para teste de transmissores de 4–20 mA seguem o mesmo princípio usado no CheckOne: fonte de 24 V, resistor de medição de precisão e leitura de tensão. O CheckOne fica alinhado ou acima da prática comum nos pontos principais:

- **Resistor de medição:** a prática usual é 250 Ω (1–5 V) ou 125 Ω em cartões de PLC, com ±0,1 %. O CheckOne usa 120 Ω ±0,1 %, o que dá uma queda de só 2,4 V a 20 mA e deixa mais tensão para o sensor.
- **Alimentação:** 24 V CC é o padrão para loops de 4–20 mA, e o CheckOne monitora tensão e corrente dessa alimentação, o que bancadas simples não fazem.
- **Proteção:** a prática recomenda proteção contra surto na entrada e limitação de corrente nas saídas. O CheckOne tem TVS, fusível e partida suave na entrada, fusível rearmável e filtro por saída, e proteção individual de cada entrada contra erro de fiação, loop invertido e descarga eletrostática.
- **Calibração:** bancadas profissionais usam calibradores de processo (como o Fluke 725) para verificar as entradas. O CheckOne tem um procedimento de calibração de zero e ganho por canal, que usa exatamente esse tipo de instrumento.
- **Isolamento:** cartões de entrada industriais costumam ter isolamento entre canais. No CheckOne, as saídas dos sensores já são isoladas, e o Iout vai ao terra da jiga, o que dispensa isolamento na própria jiga.
- **Registro e acesso remoto:** a maioria das bancadas de teste não registra nada. O CheckOne grava 48 h de histórico com data e hora e oferece página web e exportação em CSV, com várias jigas na mesma rede.

O que as soluções comerciais têm e o CheckOne não tem, por decisão de projeto: chaveamento de alimentação por canal, critério de aprovação automático e isolamento galvânico entre canais.

## 11. Itens a confirmar

Antes de liberar o projeto da placa, quatro pontos ainda dependem de verificação na peça real:

- as medidas e a furação do módulo CYD, modelado com 93 × 55 mm (o corpo do gabinete aceita no máximo ~96 mm de comprimento);
- até onde desce a parede interna das janelas dos conectores, que precisa deixar passar o corpo dos bornes (12,5 mm acima da placa);
- se as duas nervuras desenhadas dentro de cada janela de 100 mm interferem com algum borne;
- o pico de corrente de partida dos sensores, para confirmar que os fusíveis de 200 mA por canal não desarmam ao ligar;
- o controlador de tela do CYD (ST7796 ou ILI9488, conforme o lote): o firmware lê o ID do controlador na inicialização;
- o logotipo da AQTech em SVG (versão para fundo azul escuro) para a página web;
- a pinagem do conector de 26 pinos do JC4880P443C (pinos de 5 V, GND, SDA e SCL), para fechar o cabo do display externo;
- a corrente de fuga do SMAJ5.0A com 2,5 V aplicados (o datasheet especifica até 800 µA em 5 V); uma fuga estável é absorvida pela calibração.

## 12. Ideias para versões futuras

As ideias abaixo foram avaliadas e ficam registradas apenas para referência. Elas não fazem parte da placa nem do firmware atuais, e não há decisão de implementá-las.

### 12.1 Controle individual das saídas de 24 V

- **Expansor de I/O:** PCA9539 (UMW, C42420610, TSSOP-24, 16 I/O, saídas push-pull, sem pull-ups internos, endereço 0x74), com pull-down em cada pino para os canais começarem desligados. O pino de RESET vai a um GPIO do display ou a um pull-up de 10 kΩ. Conferir no datasheet da UMW a ausência de pull-ups internos.
- **Chave por canal, a definir:** (A) P-MOSFET AO3401A (Basic, 30 V) no lado positivo, com divisor de gate (10 kΩ / 4,7 kΩ) e diodo de roda livre na saída; margem de ~4% no pior surto simulado; ou (B) N-MOSFET 2N7002 (Basic, 60 V) no lado negativo, acionado direto pelo expansor com pull-down de 10 kΩ, desde que o GND de alimentação dos sensores seja isolado do corpo e da blindagem.
- **Ganhos:** desligamento rápido por firmware em curto ou com +24 V no Iin (sem esperar o PTC); volta da opção "Desligado"; partida sequencial dos sensores; medição da corrente de cada sensor pela diferença no INA226; religar um sensor pela tela ou pela web.
- **Firmware:** na inicialização, escrever o registrador de saída com todos os canais desligados antes de configurar os pinos como saída; ligar os canais um a cada ~100 ms.

### 12.2 Entrada genérica: corrente ou tensão (proxímetros com saída positiva)

- **Circuito por canal:** divisor de 33 kΩ / 10 kΩ (0,1 %) do Iin para o ADC, mais o shunt de 120 Ω ligado ao terra por um N-MOSFET AO3400A (Basic) comandado pelos outros 8 pinos do PCA9539. Shunt ligado no modo corrente e desligado no modo tensão.
- **Faixas:** tensão de 0 a ~13 V (impedância de 43 kΩ, suporta 24 V sem dano); corrente com o ganho do ADS1115 em ±1,024 V e resolução de ~1 µA.
- **Proteção:** TVS SMAJ15A no lugar do SMAJ5.0A (menor fuga e grampeamento abaixo dos 30 V do AO3400A); no modo corrente, o firmware desliga o shunt em ~10 ms se a leitura passar de 21 mA.
- **Firmware e telas:** novo tipo "Proxímetro (tensão)" com sensibilidade (V/mm) e offset configuráveis; calibração também em tensão (por exemplo, 10,000 V); indicação clara do modo de cada canal.
- **Pendente:** faixa de saída, tensão de alimentação e sensibilidade do proxímetro a ser usado.

### 12.3 Conversor ADS131M08 e acelerômetros IEPE

- **Conversor:** TI ADS131M08 (C2862610): 8 canais diferenciais, 24 bits, amostragem simultânea, até 32 kSPS, referência interna de 1,2 V, entrada de AGND − 1,3 V a AVDD (lê sinais negativos). Substitui os dois ADS1115 dos loops; o ADS1115 U3 continua para os NTC e para o diagnóstico dos sensores IEPE.
- **Shunts:** trocar os de 120 Ω por 56 Ω, 0,1 % (1,18 V a 21 mA, dentro da faixa de ±1,2 V). O loop invertido passa a ser medido com o valor real, negativo.
- **Modo tensão (proxímetro):** a entrada tem 330 kΩ nos ganhos 1 a 4; usar divisor de baixa impedância (ex.: 100 kΩ / 10 kΩ) ou um buffer.
- **Clock:** 8 MHz pelo LEDC do ESP32 (80 MHz ÷ 10) ou 8,192 MHz pelo MCLK do I²S; alternativa sem GPIO e com menos jitter: cristal de 8,192 MHz nos pinos XTAL1/XTAL2.
- **Leitura:** interrupção na borda de descida do DRDY acordando uma tarefa de alta prioridade que lê o quadro por SPI. Loops a 1–4 kSPS; acelerômetros a até 32 kSPS, com a leitura fixada num núcleo dedicado.
- **Displays:** precisa de 5 a 7 GPIOs (SPI, DRDY, clock, SYNC/RESET). Funciona com o JC3248W535 (conector P2) e com o JC4880P443C; o CYD não tem pinos livres suficientes.
- **IEPE:** reservar 2 dos 8 canais, com fonte de corrente constante de ~4 mA a partir dos 24 V, acoplamento AC (corte de ~0,5 Hz), divisor para ±1,2 V e leitura da tensão de polarização no ADS1115 para diagnóstico (aberto ~22 V, curto ~0 V, normal 8–12 V). Banda útil de ~8 kHz a 32 kSPS.
