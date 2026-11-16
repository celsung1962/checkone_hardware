# CheckOne v1 — projeto KiCad

Abre no KiCad 7, 8 ou 9 (os arquivos são do KiCad 7; o 8/9 converte ao salvar).
Abrir `CheckOne.kicad_pro`.

## Conteúdo

- `CheckOne.kicad_sch` — esquemático raiz com 4 folhas hierárquicas:
  `alimentacao` (entrada, partida suave, filtro, buck 5 V, INA226, 3,3 V, LEDs, ilhas de teste),
  `canais` (CH1–CH8: fusível, ferrite, borne, shunt, TVS, proteção da entrada),
  `adcs` (3 × ADS1115, NTC1 e NTC2),
  `display_rtc` (conectores dos três displays, RTC, bateria, furos de fixação).
  As redes são ligadas por rótulos globais com o nome da rede em cada pino.
- `CheckOne.kicad_pcb` — placa de 122 × 87 mm, 2 camadas, com todos os componentes
  posicionados, redes atribuídas (ratsnest), contorno, furos e serigrafia. **Sem trilhas.**
- `CheckOne.kicad_sym` / `CheckOne.pretty` — símbolos (AO4485 em SO-8, XL1509) e
  footprints próprios (borne KF2EDGRC-5.08-4P, DC-005-A200, suporte BS-02-A1AJ006, indutor FCH1040 de 11,5 × 10,5 mm),
  desenhados a partir dos datasheets.
- `producao/` — PDF do esquemático, imagem do posicionamento, BOM e CPL no formato da
  JLCPCB (só SMD; os PTH são soldados à mão).
- `gerador/` — scripts Python que geram tudo a partir de `design.py` (netlist única).

## Verificações feitas

- Netlist exportada pelo KiCad conferida com a netlist de projeto: 166 componentes,
  384 pinos, nenhum faltando ou em rede errada.
- Nenhuma sobreposição de componentes, exceto os bornes encostados entre si (de propósito).

## Antes de rotear (pontos de atenção)

1. Rodar o ERC e o DRC no KiCad e aplicar as regras da JLCPCB.
2. **Kelvin do INA226:** R7 e R13 (100 mΩ) lado a lado e simétricos; trilhas de medição
   do INA226 saindo do ponto médio das ilhas.
3. **Entrada:** TVS (D1) colado no conector DC; entre o SS34 (D2) e o AO4485 (Q1), só o C1.
   C2 (220 µF, gate-source) com o **+ no source** do Q1. Área de cobre no dreno do Q1.
4. **Buck:** C10/C11 colados no pino VIN do U1; laço U1–D3–L2–C12 o mais curto possível;
   cobre nos pinos 5–8 do U1 com vias para o GND.
5. **Canais:** capacitor de 100 nF de cada saída colado nos pinos +24/GND do borne;
   shunt de 120 Ω com retorno curto ao GND; plano de GND contínuo sob os ADS1115.
6. **NTC:** capacitor de 1 µF colado no conector XH.
7. Conferir no gabinete: posição dos furos do CYD (H5–H8, modelados a 87 × 49 mm) e
   do JC3248W535; posição do J4 em relação ao P1 do display.
8. **Footprints a conferir:** pacote do BAT54W (C7502705) — usado SOT-323; conector SMD
   1.25-4P LT (C668611) — usado o footprint Molex 53398 compatível.
9. **CPL:** conferir as rotações no visualizador da JLCPCB antes de confirmar o pedido.
