import base64
import sys
sys.path.insert(0, '/workspace')

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding

# Read encrypted data from file
with open('/tmp/encrypted_data.txt') as f:
 encrypted_data_b64 = f.read().strip()

with open('/tmp/encrypted_key.txt') as f:
 encrypted_key_b64 = f.read().strip()

print(f"Encrypted data (base64): {encrypted_data_b64[:50]}...")
print(f"Encrypted key (base64): {encrypted_key_b64[:50]}...")
print(f"Encrypted data length: {len(encrypted_data_b64)}")
print(f"Encrypted key length: {len(encrypted_key_b64)}")

# Decode
encrypted_data = base64.b64decode(encrypted_data_b64)
encrypted_key = base64.b64decode(encrypted_key_b64)

print(f"\nDecoded encrypted data length: {len(encrypted_data)}")
print(f"Decoded encrypted key length: {len(encrypted_key)}")

# Load private key
with open('/workspace/keys/rsa_private.pem', 'rb') as f:
 private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

# Decrypt AES key
aes_key = private_key.decrypt(
 encrypted_key,
 padding.OAEP(
 mgf=padding.MGF1(algorithm=hashes.SHA256()),
 algorithm=hashes.SHA256(),
 label=None
 )
)
print(f"\nDecrypted AES key length: {len(aes_key)}")
print(f"AES key: {aes_key.hex()}")

# Decrypt data
iv = encrypted_data[:16]
ciphertext = encrypted_data[16:]
print(f"\nIV: {iv.hex()}")
print(f"Ciphertext length: {len(ciphertext)}")

cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
decryptor = cipher.decryptor()
decrypted = decryptor.update(ciphertext) + decryptor.finalize()

# Unpad
unpadder = sym_padding.PKCS7(128).unpadder()
unpadded = unpadder.update(decrypted) + unpadder.finalize()

print(f"\nDecrypted: {unpadded.decode('utf-8')}")
print("\n=== SUCCESS! ===")
