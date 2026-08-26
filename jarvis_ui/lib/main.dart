import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

void main() {
  runApp(const JarvisApp());
}

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'J.A.R.V.I.S OS - Cyberpunk HUD',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF030305),
        fontFamily: 'Consolas',
      ),
      home: const JarvisDashboard(),
    );
  }
}

class JarvisDashboard extends StatefulWidget {
  const JarvisDashboard({super.key});

  @override
  State<JarvisDashboard> createState() => _JarvisDashboardState();
}

class _JarvisDashboardState extends State<JarvisDashboard>
    with TickerProviderStateMixin {
  WebSocketChannel? _channel;
  bool _isConnected = false;
  Timer? _reconnectTimer;

  String _jarvisState = 'idle';
  bool _faceRecognized = true;
  String _recognizedUser = 'TAB & TECH';
  double _audioLevel = 0.5;

  double _cpuLoad = 0.42;
  double _ramLoad = 0.55;
  double _gpuLoad = 0.78;
  double _latency = 0.12;

  final List<Map<String, String>> _terminalLogs = [
    {'type': 'sys', 'msg': 'SYSTEM BOOT: J.A.R.V.I.S OS v3.5 ONLINE'},
    {'type': 'face', 'msg': 'FACE ID MODULE: SCANNER READY'},
    {'type': 'voice', 'msg': 'VOICE DUPLEX: AWAITING AUDIO STREAM'},
  ];

  late AnimationController _rotationController;
  late AnimationController _pulseController;
  late AnimationController _waveController;
  late AnimationController _scannerController;

  @override
  void initState() {
    super.initState();

    _rotationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 12),
    )..repeat();

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);

    _waveController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat();

    _scannerController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);

    _connectWebSocket();
  }

  void _connectWebSocket() {
    _reconnectTimer?.cancel();

    try {
      final uri = Uri.parse('ws://localhost:8765');
      _channel = WebSocketChannel.connect(uri);

      // Handle socket connection ready or error cleanly
      _channel!.ready.then((_) {
        if (mounted) {
          setState(() {
            _isConnected = true;
            _logToTerminal('sys', 'WebSocket connected to Python Core (Port 8765).');
          });
        }
      }).catchError((error) {
        if (mounted && _isConnected) {
          setState(() { _isConnected = false; });
        }
        _scheduleReconnect();
      });

      _channel!.stream.listen(
        (message) {
          try {
            final data = jsonDecode(message);
            if (data['type'] == 'status') {
              setState(() {
                _jarvisState = data['state'] ?? 'idle';
                if (data['user'] != null) {
                  _recognizedUser = data['user'];
                  _faceRecognized = true;
                }
                _updateStateAnimation(_jarvisState);
              });
            } else if (data['type'] == 'telemetry') {
              setState(() {
                if (data['cpu'] != null) _cpuLoad = (data['cpu'] as num).toDouble() / 100.0;
                if (data['ram'] != null) _ramLoad = (data['ram'] as num).toDouble() / 100.0;
                if (data['gpu'] != null) _gpuLoad = (data['gpu'] as num).toDouble() / 100.0;
                if (data['latency'] != null) _latency = (data['latency'] as num).toDouble() / 100.0;
              });
            }
            if (data['audio_level'] != null) {
              setState(() {
                _audioLevel = (data['audio_level'] as num).toDouble();
              });
            }
            if (data['message'] != null) {
              _logToTerminal(data['type'] ?? 'info', data['message']);
            }
          } catch (e) {
            _logToTerminal('err', 'Raw Data: $message');
          }
        },
        onError: (error) {
          if (_isConnected && mounted) {
            setState(() { _isConnected = false; });
            _logToTerminal('err', 'Server connection lost. Auto-reconnecting...');
          }
          _scheduleReconnect();
        },
        onDone: () {
          if (_isConnected && mounted) {
            setState(() { _isConnected = false; _jarvisState = 'idle'; });
            _logToTerminal('sys', 'Server offline. Retrying in 3s...');
          }
          _scheduleReconnect();
        },
        cancelOnError: true,
      );
    } catch (e) {
      if (mounted) {
        setState(() { _isConnected = false; });
      }
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (!_isConnected && mounted) {
        _connectWebSocket();
      }
    });
  }

  void _updateStateAnimation(String state) {
    switch (state) {
      case 'listening':
        _pulseController.duration = const Duration(milliseconds: 500);
        _rotationController.duration = const Duration(seconds: 6);
        break;
      case 'processing':
        _pulseController.duration = const Duration(milliseconds: 300);
        _rotationController.duration = const Duration(seconds: 3);
        break;
      case 'speaking':
        _pulseController.duration = const Duration(milliseconds: 700);
        _rotationController.duration = const Duration(seconds: 8);
        break;
      case 'face_scanning':
        _pulseController.duration = const Duration(milliseconds: 400);
        _rotationController.duration = const Duration(seconds: 4);
        break;
      default:
        _pulseController.duration = const Duration(milliseconds: 1500);
        _rotationController.duration = const Duration(seconds: 14);
    }
    _pulseController.repeat(reverse: true);
    _rotationController.repeat();
  }

  void _logToTerminal(String type, String message) {
    setState(() {
      _terminalLogs.add({'type': type, 'msg': '> $message'});
      if (_terminalLogs.length > 50) _terminalLogs.removeAt(0);
    });
  }

  void _sendCommand(String command, {Map<String, dynamic>? extra}) {
    if (_isConnected && _channel != null) {
      final payload = {'command': command, ...?extra};
      _channel!.sink.add(jsonEncode(payload));
      _logToTerminal('cmd', 'Sent command: $command');
    } else {
      _logToTerminal('sys', 'Server offline. Reconnecting before command...');
      _connectWebSocket();
    }
  }

  void _setSimulatedState(String state) {
    setState(() {
      _jarvisState = state;
      _updateStateAnimation(state);
      if (state == 'face_scanning') {
        _logToTerminal('face', 'FACE ID SCAN IN PROGRESS...');
      } else if (state == 'listening') {
        _logToTerminal('voice', 'VOICE ENGINE LISTENING...');
      } else if (state == 'speaking') {
        _logToTerminal('voice', 'JARVIS RESPONDING VIA TTS...');
      } else if (state == 'processing') {
        _logToTerminal('sys', 'AI CORE PROCESSING INFERENCE...');
      }
    });
  }

  @override
  void dispose() {
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _rotationController.dispose();
    _pulseController.dispose();
    _waveController.dispose();
    _scannerController.dispose();
    super.dispose();
  }

  Color get _accentColor {
    switch (_jarvisState) {
      case 'listening':
        return const Color(0xFF00E5FF);
      case 'processing':
        return const Color(0xFF00FF66);
      case 'speaking':
        return const Color(0xFFD946EF);
      case 'face_scanning':
        return const Color(0xFFFFB703);
      case 'alert':
        return const Color(0xFFFF2A6D);
      default:
        return const Color(0xFF00E5FF);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: Container(
              decoration: const BoxDecoration(
                gradient: RadialGradient(
                  colors: [
                    Color(0xFF0D111E),
                    Color(0xFF05070C),
                    Color(0xFF020204)
                  ],
                  stops: [0.0, 0.6, 1.0],
                  radius: 1.3,
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: CustomPaint(
              painter: BackgroundGridPainter(accentColor: _accentColor),
            ),
          ),
          SafeArea(
            child: Column(
              children: [
                _buildTopHeader(),
                Expanded(
                  child: Row(
                    children: [
                      _buildLeftHUD(),
                      Expanded(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            _buildHolographicCoreHUD(),
                            const SizedBox(height: 12),
                            _buildVoiceWaveformSpectrum(),
                          ],
                        ),
                      ),
                      _buildRightHUD(),
                    ],
                  ),
                ),
                _buildBottomTerminal(),
              ],
            ),
          ),
        ],
      ),
    );
  }
  Widget _buildTopHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF0A0E1A).withOpacity(0.6),
        border: Border(
          bottom: BorderSide(
            color: _accentColor.withOpacity(0.3),
            width: 1.5,
          ),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _accentColor.withOpacity(0.2),
                  border: Border.all(color: _accentColor),
                ),
                child: Icon(Icons.blur_on_rounded,
                    color: _accentColor, size: 20),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'J.A.R.V.I.S  //  AI DUPLEX OS',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w900,
                      color: _accentColor,
                      letterSpacing: 2.5,
                      shadows: [
                        Shadow(
                          color: _accentColor.withOpacity(0.8),
                          blurRadius: 10,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 2),
                  const Text(
                    'QUANTUM CORE V3.5 • VOICE & FACE BIOMETRICS INTEGRATED',
                    style: TextStyle(
                      fontSize: 9,
                      color: Color(0xFF64748B),
                      letterSpacing: 1.5,
                    ),
                  ),
                ],
              ),
            ],
          ),
          Row(
            children: [
              _buildHeaderBadge(
                label: 'MODE: ${_jarvisState.toUpperCase()}',
                color: _accentColor,
                icon: Icons.graphic_eq_rounded,
              ),
              const SizedBox(width: 12),
              GestureDetector(
                onTap: () {
                  _logToTerminal('sys', 'Manual reconnection triggered...');
                  _connectWebSocket();
                },
                child: MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: _buildHeaderBadge(
                    label: _isConnected ? 'WS ONLINE' : 'CLICK TO RECONNECT',
                    color: _isConnected
                        ? const Color(0xFF00FF66)
                        : const Color(0xFFFF2A6D),
                    icon: _isConnected
                        ? Icons.wifi_rounded
                        : Icons.refresh_rounded,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildHeaderBadge(
      {required String label, required Color color, required IconData icon}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withOpacity(0.5)),
        boxShadow: [
          BoxShadow(
            color: color.withOpacity(0.2),
            blurRadius: 8,
          ),
        ],
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 14),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.bold,
              letterSpacing: 1.2,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLeftHUD() {
    return Container(
      width: 260,
      margin: const EdgeInsets.only(left: 14, top: 10, bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF060913).withOpacity(0.7),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF1E293B)),
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildSectionHeader('FACE RECOGNITION HUD', Icons.face_retouching_natural),
            const SizedBox(height: 8),
            Container(
              height: 115,
              width: double.infinity,
              decoration: BoxDecoration(
                color: Colors.black.withOpacity(0.6),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: _accentColor.withOpacity(0.4)),
              ),
              child: AnimatedBuilder(
                animation: _scannerController,
                builder: (context, child) {
                  return CustomPaint(
                    painter: FaceScannerPainter(
                      scanProgress: _scannerController.value,
                      isScanning: _jarvisState == 'face_scanning',
                      isRecognized: _faceRecognized,
                      accentColor: _accentColor,
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'TARGET ID:',
                  style: TextStyle(color: Color(0xFF64748B), fontSize: 10),
                ),
                Text(
                  _faceRecognized ? _recognizedUser : 'UNIDENTIFIED',
                  style: TextStyle(
                    color: _faceRecognized
                        ? const Color(0xFF00FF66)
                        : const Color(0xFFFF2A6D),
                    fontWeight: FontWeight.bold,
                    fontSize: 10,
                    letterSpacing: 1.1,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'BIOMETRIC LOCK:',
                  style: TextStyle(color: Color(0xFF64748B), fontSize: 10),
                ),
                Text(
                  _faceRecognized ? 'VERIFIED (99.8%)' : 'LOCKED',
                  style: TextStyle(
                    color: _faceRecognized
                        ? const Color(0xFF00E5FF)
                        : const Color(0xFFFF2A6D),
                    fontWeight: FontWeight.bold,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
            const Divider(color: Color(0xFF1E293B), height: 16),
            _buildSectionHeader('VOICE AUTH MODULE', Icons.graphic_eq),
            const SizedBox(height: 6),
            _buildMetricRow('MIC STATUS', 'ACTIVE / DUPLEX'),
            _buildMetricRow('SAMPLE RATE', '16 kHz / 16-BIT'),
            _buildMetricRow('NOISE CANCEL', 'QUANTUM FILTER ON'),
            _buildMetricRow('SPEAKER AUTH', 'VOICEPRINT MATCHED'),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: _buildSmallNeonButton(
                    'FACE SCAN',
                    const Color(0xFFFFB703),
                    () => _setSimulatedState('face_scanning'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _buildSmallNeonButton(
                    'VOICE TEST',
                    const Color(0xFF00E5FF),
                    () => _setSimulatedState('listening'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRightHUD() {
    return Container(
      width: 250,
      margin: const EdgeInsets.only(right: 14, top: 10, bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF060913).withOpacity(0.7),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF1E293B)),
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildSectionHeader('SYSTEM TELEMETRY', Icons.developer_board),
            const SizedBox(height: 8),
            _buildTelemetryBar('CPU CORE LOAD', _cpuLoad, const Color(0xFF00E5FF)),
            _buildTelemetryBar('NEURAL MEMORY', _ramLoad, const Color(0xFFA855F7)),
            _buildTelemetryBar('GPU ACCELERATION', _gpuLoad, const Color(0xFF00FF66)),
            _buildTelemetryBar('LATENCY (MS)', _latency, const Color(0xFFFFB703)),
            const Divider(color: Color(0xFF1E293B), height: 16),
            _buildSectionHeader('SIMULATE STATES', Icons.tune),
            const SizedBox(height: 6),
            _buildSimStateButton('IDLE STATE', 'idle', const Color(0xFF64748B)),
            const SizedBox(height: 4),
            _buildSimStateButton('LISTENING...', 'listening', const Color(0xFF00E5FF)),
            const SizedBox(height: 4),
            _buildSimStateButton('PROCESSING...', 'processing', const Color(0xFF00FF66)),
            const SizedBox(height: 4),
            _buildSimStateButton('SPEAKING...', 'speaking', const Color(0xFFD946EF)),
            const SizedBox(height: 10),
            _buildSmallNeonButton(
              'INITIALIZE DUPLEX',
              const Color(0xFF00E5FF),
              () => _sendCommand('initialize'),
            ),
            const SizedBox(height: 6),
            _buildSmallNeonButton(
              'FORCE OVERRIDE',
              const Color(0xFFFF2A6D),
              () => _sendCommand('stop'),
            ),
          ],
        ),
      ),
    );
  }
  Widget _buildSimStateButton(String label, String state, Color color) {
    final isCurrent = _jarvisState == state;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => _setSimulatedState(state),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 7, horizontal: 10),
          decoration: BoxDecoration(
            color: isCurrent ? color.withOpacity(0.2) : Colors.black26,
            borderRadius: BorderRadius.circular(4),
            border: Border.all(
              color: isCurrent ? color : color.withOpacity(0.3),
            ),
          ),
          child: Row(
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isCurrent ? color : Colors.grey,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  color: isCurrent ? Colors.white : const Color(0xFF94A3B8),
                  fontSize: 10,
                  fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
                  letterSpacing: 1.1,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHolographicCoreHUD() {
    return AnimatedBuilder(
      animation: Listenable.merge(
          [_rotationController, _pulseController, _waveController]),
      builder: (context, child) {
        return SizedBox(
          width: 270,
          height: 270,
          child: CustomPaint(
            painter: ArcReactorCorePainter(
              rotationValue: _rotationController.value,
              pulseValue: _pulseController.value,
              waveValue: _waveController.value,
              state: _jarvisState,
              accentColor: _accentColor,
            ),
          ),
        );
      },
    );
  }

  Widget _buildVoiceWaveformSpectrum() {
    return AnimatedBuilder(
      animation: _waveController,
      builder: (context, child) {
        return Container(
          width: 320,
          height: 40,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
          decoration: BoxDecoration(
            color: const Color(0xFF060913).withOpacity(0.5),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: _accentColor.withOpacity(0.3)),
          ),
          child: CustomPaint(
            painter: AudioWaveformPainter(
              waveProgress: _waveController.value,
              state: _jarvisState,
              accentColor: _accentColor,
              audioLevel: _audioLevel,
            ),
          ),
        );
      },
    );
  }

  Widget _buildBottomTerminal() {
    return Container(
      height: 115,
      margin: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF04060C).withOpacity(0.85),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFF1E293B)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.7),
            blurRadius: 10,
            spreadRadius: 2,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  const Icon(Icons.terminal_rounded,
                      color: Color(0xFF64748B), size: 14),
                  const SizedBox(width: 8),
                  Text(
                    'TERMINAL LOG STREAM',
                    style: TextStyle(
                      color: _accentColor,
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.5,
                    ),
                  ),
                ],
              ),
              Text(
                'LOG COUNT: ${_terminalLogs.length}',
                style: const TextStyle(color: Color(0xFF64748B), fontSize: 9),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Expanded(
            child: ListView.builder(
              reverse: true,
              itemCount: _terminalLogs.length,
              itemBuilder: (context, index) {
                final logObj =
                    _terminalLogs[_terminalLogs.length - 1 - index];
                final msg = logObj['msg'] ?? '';
                final type = logObj['type'] ?? 'info';

                Color logColor = const Color(0xFF94A3B8);
                if (type == 'sys') logColor = const Color(0xFF00E5FF);
                if (type == 'face') logColor = const Color(0xFFFFB703);
                if (type == 'voice') logColor = const Color(0xFFD946EF);
                if (type == 'err') logColor = const Color(0xFFFF2A6D);
                if (type == 'cmd') logColor = const Color(0xFF00FF66);

                return Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Text(
                    msg,
                    style: TextStyle(
                      color: logColor,
                      fontSize: 10,
                      fontFamily: 'Consolas',
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title, IconData icon) {
    return Row(
      children: [
        Icon(icon, color: _accentColor, size: 13),
        const SizedBox(width: 6),
        Text(
          title,
          style: TextStyle(
            color: _accentColor,
            fontSize: 10,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.3,
          ),
        ),
      ],
    );
  }

  Widget _buildMetricRow(String label, String val) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: const TextStyle(color: Color(0xFF64748B), fontSize: 9)),
          Text(val,
              style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 9,
                  fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }

  Widget _buildTelemetryBar(String label, double val, Color color) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label,
                  style: const TextStyle(
                      color: Color(0xFF64748B), fontSize: 9)),
              Text('${(val * 100).toInt()}%',
                  style: TextStyle(
                      color: color,
                      fontSize: 9,
                      fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 3),
          ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: LinearProgressIndicator(
              value: val.clamp(0.0, 1.0),
              minHeight: 4,
              backgroundColor: Colors.black45,
              valueColor: AlwaysStoppedAnimation<Color>(color),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSmallNeonButton(
      String text, Color color, VoidCallback onTap) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: color.withOpacity(0.08),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: color.withOpacity(0.6), width: 1.2),
            boxShadow: [
              BoxShadow(
                color: color.withOpacity(0.2),
                blurRadius: 8,
              ),
            ],
          ),
          child: Text(
            text,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: color,
              fontSize: 10,
              fontWeight: FontWeight.bold,
              letterSpacing: 1.2,
            ),
          ),
        ),
      ),
    );
  }
}

class ArcReactorCorePainter extends CustomPainter {
  final double rotationValue;
  final double pulseValue;
  final double waveValue;
  final String state;
  final Color accentColor;

  ArcReactorCorePainter({
    required this.rotationValue,
    required this.pulseValue,
    required this.waveValue,
    required this.state,
    required this.accentColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.width / 2 - 10;

    final Paint tickPaint = Paint()
      ..color = accentColor.withOpacity(0.3)
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;

    final double outerAngle = rotationValue * 2 * math.pi;
    for (int i = 0; i < 36; i++) {
      final angle = outerAngle + (i * (math.pi / 18));
      final innerP = Offset(
        center.dx + (maxRadius - 10) * math.cos(angle),
        center.dy + (maxRadius - 10) * math.sin(angle),
      );
      final outerP = Offset(
        center.dx + maxRadius * math.cos(angle),
        center.dy + maxRadius * math.sin(angle),
      );
      canvas.drawLine(innerP, outerP, tickPaint);
    }

    final Paint arcPaint = Paint()
      ..color = accentColor.withOpacity(0.7)
      ..strokeWidth = 3.0
      ..style = PaintingStyle.stroke;

    final double counterAngle = -rotationValue * 4 * math.pi;
    final Rect arcRect = Rect.fromCircle(center: center, radius: maxRadius - 18);
    canvas.drawArc(arcRect, counterAngle, math.pi / 2, false, arcPaint);
    canvas.drawArc(arcRect, counterAngle + math.pi, math.pi / 2, false, arcPaint);

    final double pulseRadius = (maxRadius - 38) + (pulseValue * 12);
    final Paint glowPaint = Paint()
      ..color = accentColor.withOpacity(0.25 + (pulseValue * 0.25))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 5.0
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10);
    canvas.drawCircle(center, pulseRadius, glowPaint);

    final int rayCount = 40;
    final Paint rayPaint = Paint()
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round;

    for (int i = 0; i < rayCount; i++) {
      final angle = (i * (2 * math.pi / rayCount));
      final waveOffset = math.sin((i * 0.4) + (waveValue * 2 * math.pi));
      final rayLength = 6 + (waveOffset.abs() * (state == 'speaking' || state == 'listening' ? 22 : 6));

      rayPaint.color = accentColor.withOpacity(0.5 + (waveOffset.abs() * 0.5));

      final r1 = maxRadius - 52;
      final r2 = r1 + rayLength;

      final p1 = Offset(center.dx + r1 * math.cos(angle), center.dy + r1 * math.sin(angle));
      final p2 = Offset(center.dx + r2 * math.cos(angle), center.dy + r2 * math.sin(angle));
      canvas.drawLine(p1, p2, rayPaint);
    }

    final Paint innerRingPaint = Paint()
      ..color = accentColor.withOpacity(0.8)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5;
    canvas.drawCircle(center, maxRadius - 60, innerRingPaint);

    final Paint centerGlow = Paint()
      ..color = accentColor.withOpacity(0.85)
      ..style = PaintingStyle.fill
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 18);
    canvas.drawCircle(center, 30 + (pulseValue * 8), centerGlow);

    final Paint centerCore = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.fill;
    canvas.drawCircle(center, 10, centerCore);
  }

  @override
  bool shouldRepaint(covariant ArcReactorCorePainter oldDelegate) => true;
}

class FaceScannerPainter extends CustomPainter {
  final double scanProgress;
  final bool isScanning;
  final bool isRecognized;
  final Color accentColor;

  FaceScannerPainter({
    required this.scanProgress,
    required this.isScanning,
    required this.isRecognized,
    required this.accentColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;

    final Paint bracketPaint = Paint()
      ..color = isRecognized ? const Color(0xFF00FF66) : accentColor
      ..strokeWidth = 2.5
      ..style = PaintingStyle.stroke;

    const len = 14.0;
    canvas.drawLine(const Offset(8, 8), const Offset(8 + len, 8), bracketPaint);
    canvas.drawLine(const Offset(8, 8), const Offset(8, 8 + len), bracketPaint);
    canvas.drawLine(Offset(w - 8, 8), Offset(w - 8 - len, 8), bracketPaint);
    canvas.drawLine(Offset(w - 8, 8), Offset(w - 8, 8 + len), bracketPaint);
    canvas.drawLine(Offset(8, h - 8), Offset(8 + len, h - 8), bracketPaint);
    canvas.drawLine(Offset(8, h - 8), Offset(8, h - 8 - len), bracketPaint);
    canvas.drawLine(Offset(w - 8, h - 8), Offset(w - 8 - len, h - 8), bracketPaint);
    canvas.drawLine(Offset(w - 8, h - 8), Offset(w - 8, h - 8 - len), bracketPaint);

    final Paint boxPaint = Paint()
      ..color = (isRecognized ? const Color(0xFF00FF66) : accentColor).withOpacity(0.3)
      ..strokeWidth = 1.0
      ..style = PaintingStyle.stroke;
    final Rect targetRect = Rect.fromCenter(
        center: Offset(w / 2, h / 2), width: w * 0.5, height: h * 0.6);
    canvas.drawRect(targetRect, boxPaint);

    final scanY = 12 + (scanProgress * (h - 24));
    final Paint beamPaint = Paint()
      ..color = isScanning ? const Color(0xFFFFB703) : accentColor.withOpacity(0.8)
      ..strokeWidth = 2.0
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
    canvas.drawLine(Offset(12, scanY), Offset(w - 12, scanY), beamPaint);

    final textPainter = TextPainter(
      text: TextSpan(
        text: isScanning ? 'SCANNING FACE...' : (isRecognized ? 'FACE MATCHED' : 'READY'),
        style: TextStyle(
          color: isRecognized ? const Color(0xFF00FF66) : accentColor,
          fontSize: 9,
          fontWeight: FontWeight.bold,
          letterSpacing: 1.2,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    textPainter.paint(canvas, Offset(w / 2 - textPainter.width / 2, h - 20));
  }

  @override
  bool shouldRepaint(covariant FaceScannerPainter oldDelegate) => true;
}

class AudioWaveformPainter extends CustomPainter {
  final double waveProgress;
  final String state;
  final Color accentColor;
  final double audioLevel;

  AudioWaveformPainter({
    required this.waveProgress,
    required this.state,
    required this.accentColor,
    required this.audioLevel,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final barCount = 30;
    final barWidth = size.width / (barCount * 1.6);
    final midY = size.height / 2;

    final Paint barPaint = Paint()..strokeCap = StrokeCap.round;

    for (int i = 0; i < barCount; i++) {
      final x = i * (barWidth * 1.6) + barWidth;

      double heightFactor = math.sin((i * 0.3) + (waveProgress * 2 * math.pi)).abs();
      if (state == 'speaking' || state == 'listening') {
        heightFactor = (heightFactor * 0.7) + (audioLevel * 0.3);
      } else {
        heightFactor *= 0.25;
      }

      final barHeight = (size.height * 0.8) * heightFactor;
      barPaint.color = accentColor.withOpacity(0.4 + (heightFactor * 0.6));
      barPaint.strokeWidth = barWidth;

      canvas.drawLine(
        Offset(x, midY - (barHeight / 2)),
        Offset(x, midY + (barHeight / 2)),
        barPaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant AudioWaveformPainter oldDelegate) => true;
}

class BackgroundGridPainter extends CustomPainter {
  final Color accentColor;

  BackgroundGridPainter({required this.accentColor});

  @override
  void paint(Canvas canvas, Size size) {
    final gridPaint = Paint()
      ..color = accentColor.withOpacity(0.03)
      ..strokeWidth = 1.0;

    const step = 40.0;
    for (double x = 0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (double y = 0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }
  }

  @override
  bool shouldRepaint(covariant BackgroundGridPainter oldDelegate) => false;
}
