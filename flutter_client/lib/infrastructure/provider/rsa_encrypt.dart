import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:pointycastle/asn1.dart';
import 'package:pointycastle/export.dart';

/// Encrypts [value] with an SPKI PEM public key using RSA-OAEP/SHA-256.
///
/// The backend decrypts the base64 result with the matching private key, so
/// secrets never travel in plaintext.
String encryptWithPublicKey(String value, String pem) {
  final der = base64Decode(
    pem
        .split('\n')
        .where((line) => !line.startsWith('-----'))
        .join()
        .replaceAll(RegExp(r'\s'), ''),
  );
  final spki = ASN1Parser(der).nextObject() as ASN1Sequence;
  final bits = spki.elements![1] as ASN1BitString;
  final rsa =
      ASN1Parser(Uint8List.fromList(bits.stringValues!)).nextObject()
          as ASN1Sequence;
  final key = RSAPublicKey(
    (rsa.elements![0] as ASN1Integer).integer!,
    (rsa.elements![1] as ASN1Integer).integer!,
  );
  final random = Random.secure();
  final cipher = OAEPEncoding.withSHA256(RSAEngine())
    ..init(
      true,
      ParametersWithRandom(
        PublicKeyParameter<RSAPublicKey>(key),
        FortunaRandom()..seed(
          KeyParameter(
            Uint8List.fromList(
              List<int>.generate(32, (_) => random.nextInt(256)),
            ),
          ),
        ),
      ),
    );
  return base64Encode(cipher.process(Uint8List.fromList(utf8.encode(value))));
}
