import 'package:flutter/material.dart';

import '../domain/models/capability.dart';

/// Grouped capability entries shared by the persistent rail and the drawer.
class CapabilityNav extends StatelessWidget {
  const CapabilityNav({
    required this.capabilities,
    required this.activeId,
    required this.onSelected,
    super.key,
  });

  final List<Capability> capabilities;
  final String activeId;
  final ValueChanged<Capability> onSelected;

  static const _groupLabels = <CapabilityGroup, String>{
    CapabilityGroup.workspace: '工作区',
    CapabilityGroup.creation: '创作',
    CapabilityGroup.data: '数据',
    CapabilityGroup.system: '系统',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 12),
      children: [
        for (final group in CapabilityGroup.values)
          if (capabilities.any((capability) => capability.group == group)) ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
              child: Text(
                _groupLabels[group]!,
                style: theme.textTheme.bodySmall,
              ),
            ),
            for (final capability in capabilities)
              if (capability.group == group)
                ListTile(
                  key: Key('capabilityNav_${capability.id}'),
                  dense: true,
                  selected: capability.id == activeId,
                  leading: Icon(capability.icon, size: 20),
                  title: Text(capability.label),
                  onTap: () => onSelected(capability),
                ),
          ],
      ],
    );
  }
}
