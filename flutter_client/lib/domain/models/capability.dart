import 'package:flutter/widgets.dart';

enum CapabilityGroup { workspace, creation, data, system }

enum CapabilityAccess { normal, admin, superadmin }

/// A navigable workbench module declared once and rendered by the shell.
class Capability {
  const Capability({
    required this.id,
    required this.label,
    required this.icon,
    required this.group,
    required this.builder,
    this.access = CapabilityAccess.normal,
  });

  final String id;
  final String label;
  final IconData icon;
  final CapabilityGroup group;
  final CapabilityAccess access;

  /// Creates the page lazily, so unopened modules never run their requests.
  final Widget Function() builder;
}
