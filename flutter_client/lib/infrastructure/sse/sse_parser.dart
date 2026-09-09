import 'dart:convert';

class SseEvent {
  const SseEvent({
    required this.type,
    required this.raw,
    this.data,
  });

  final String type;
  final String raw;
  final Map<String, dynamic>? data;
}

/// Incremental SSE parser for `data: {json}\\n\\n` Agent frames.
class SseParser {
  final StringBuffer _buffer = StringBuffer();

  List<SseEvent> push(String chunk) {
    _buffer.write(chunk);
    final combined = _buffer.toString().replaceAll('\r\n', '\n');
    final events = <SseEvent>[];

    var remaining = combined;
    while (true) {
      final separator = remaining.indexOf('\n\n');
      if (separator < 0) {
        break;
      }
      final frame = remaining.substring(0, separator);
      remaining = remaining.substring(separator + 2);
      final event = _parseFrame(frame);
      if (event != null) {
        events.add(event);
      }
    }

    _buffer
      ..clear()
      ..write(remaining);
    return events;
  }

  void reset() {
    _buffer.clear();
  }

  SseEvent? _parseFrame(String frame) {
    final dataLines = <String>[];
    for (final rawLine in frame.split('\n')) {
      final line = rawLine.trimRight();
      if (line.startsWith('data:')) {
        var payload = line.substring(5);
        if (payload.startsWith(' ')) {
          payload = payload.substring(1);
        }
        dataLines.add(payload);
      }
    }
    if (dataLines.isEmpty) {
      return null;
    }

    final raw = dataLines.join('\n');
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        return _fromMap(decoded, raw);
      }
      if (decoded is Map) {
        return _fromMap(Map<String, dynamic>.from(decoded), raw);
      }
    } on FormatException {
      return SseEvent(type: 'message', raw: raw);
    }
    return SseEvent(type: 'message', raw: raw);
  }

  SseEvent _fromMap(Map<String, dynamic> decoded, String raw) {
    final type = decoded['type'] as String? ?? 'message';
    final dataField = decoded['data'];
    Map<String, dynamic>? data;
    if (dataField is Map<String, dynamic>) {
      data = dataField;
    } else if (dataField is Map) {
      data = Map<String, dynamic>.from(dataField);
    } else if (dataField != null) {
      data = <String, dynamic>{'value': dataField};
    } else {
      final rest = Map<String, dynamic>.from(decoded)..remove('type');
      data = rest.isEmpty ? null : rest;
    }
    return SseEvent(type: type, raw: raw, data: data);
  }
}
