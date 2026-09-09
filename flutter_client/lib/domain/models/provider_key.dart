class ProviderKeySummary {
  const ProviderKeySummary({
    required this.token,
    required this.provider,
    required this.status,
    required this.enabled,
    required this.expiresAt,
    this.remark = '',
  });

  final String token;
  final String provider;
  final String status;
  final bool enabled;
  final DateTime? expiresAt;
  final String remark;

  bool get isUsable =>
      token.isNotEmpty &&
      enabled &&
      status != 'expired' &&
      status != 'invalid' &&
      (expiresAt == null || expiresAt!.isAfter(DateTime.now()));

  factory ProviderKeySummary.fromJson(Map<String, dynamic> json) {
    return ProviderKeySummary(
      token: json['token']?.toString() ?? '',
      provider: json['provider']?.toString() ?? '',
      status: json['status']?.toString() ?? 'unknown',
      enabled: json['enabled'] == true,
      expiresAt: DateTime.tryParse(json['expires_at']?.toString() ?? ''),
      remark: json['remark']?.toString() ?? '',
    );
  }
}
