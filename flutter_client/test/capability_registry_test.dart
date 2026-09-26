import 'package:codingmatrix_desktop/application/capability_registry.dart';
import 'package:codingmatrix_desktop/domain/models/capability.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('能力标识唯一', () {
    final ids = capabilityRegistry.map((capability) => capability.id).toList();
    expect(ids.toSet().length, ids.length);
  });

  test('每项能力都归入声明过的分组', () {
    for (final capability in capabilityRegistry) {
      expect(CapabilityGroup.values, contains(capability.group));
    }
  });

  test('normal 会话看不到管理员后台与 MCP 管理', () {
    final ids = visibleCapabilities(
      'normal',
    ).map((capability) => capability.id).toList();
    expect(ids, contains('agent'));
    expect(ids, isNot(contains('admin')));
    expect(ids, isNot(contains('mcp')));
  });

  test('admin 会话可见管理员后台但看不到 MCP 管理', () {
    final ids = visibleCapabilities(
      'admin',
    ).map((capability) => capability.id).toList();
    expect(ids, contains('admin'));
    expect(ids, isNot(contains('mcp')));
  });

  test('superadmin 按注册表顺序看到全部能力', () {
    expect(
      visibleCapabilities('superadmin').map((capability) => capability.id),
      capabilityRegistry.map((capability) => capability.id),
    );
  });

  test('未知权限只看到 normal 能力', () {
    final visible = visibleCapabilities(null);
    expect(visible, isNotEmpty);
    expect(
      visible.every(
        (capability) => capability.access == CapabilityAccess.normal,
      ),
      isTrue,
    );
  });
}
