import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/auth_controller.dart';
import '../application/capability_registry.dart';
import '../application/workbench_controller.dart';
import '../domain/models/capability.dart';
import 'account_overlays.dart';
import 'capability_nav.dart';
import 'shell_scaffold.dart';

/// Application shell: renders the grouped capability navigation and keeps the
/// opened capability pages alive in an [IndexedStack].
class WorkbenchPage extends ConsumerStatefulWidget {
  const WorkbenchPage({super.key});

  @override
  ConsumerState<WorkbenchPage> createState() => _WorkbenchPageState();
}

class _WorkbenchPageState extends ConsumerState<WorkbenchPage> {
  static const _wideBreakpoint = 900.0;

  final _scaffoldKey = GlobalKey<ScaffoldState>();
  final Map<String, Widget> _panes = <String, Widget>{};
  final List<String> _openIds = <String>[];
  final List<String> _history = <String>[];
  String _activeId = 'agent';
  bool _drawerOpen = false;

  void _resetAccount() {
    closeAccountOverlays(context);
    _panes.clear();
    _openIds.clear();
    _history.clear();
    _activeId = 'agent';
    _drawerOpen = false;
  }

  void _select(Capability capability, {required bool wide}) {
    if (!wide) {
      _scaffoldKey.currentState?.closeDrawer();
    }
    setState(() {
      if (capability.id == 'agent') {
        _history.clear();
      } else if (capability.id != _activeId) {
        _history.remove(capability.id);
        _history.add(_activeId);
      }
      if (!_panes.containsKey(capability.id)) {
        _panes[capability.id] = capability.builder();
        _openIds.add(capability.id);
      }
      _activeId = capability.id;
    });
  }

  void _goBack() {
    if (_history.isNotEmpty) {
      final target = _history.removeLast();
      setState(() => _activeId = target);
      return;
    }
    if (_activeId != 'agent') {
      setState(() => _activeId = 'agent');
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(
      authControllerProvider.select((s) => s.session?.accessTokenRef),
      (_, __) => _resetAccount(),
    );
    ref.listen(apiBaseUrlProvider, (_, __) => _resetAccount());
    final session = ref.watch(authControllerProvider).session;
    final visible = visibleCapabilities(session?.permissionLevel);

    // Drop panes the current session may no longer see, then fall back to the
    // always-visible Agent home when the active capability is gone.
    final visibleIds = visible.map((capability) => capability.id).toSet();
    _openIds.removeWhere((id) {
      if (visibleIds.contains(id)) return false;
      _panes.remove(id);
      return true;
    });
    _history.removeWhere((id) => !visibleIds.contains(id));
    if (!visibleIds.contains(_activeId)) {
      _activeId = 'agent';
    }
    final active = visible.firstWhere(
      (capability) => capability.id == _activeId,
      orElse: () => visible.first,
    );
    _activeId = active.id;
    if (!_panes.containsKey(active.id)) {
      _panes[active.id] = active.builder();
      _openIds.add(active.id);
    }

    final wide = MediaQuery.sizeOf(context).width >= _wideBreakpoint;
    final nav = CapabilityNav(
      capabilities: visible,
      activeId: _activeId,
      onSelected: (capability) => _select(capability, wide: wide),
    );
    final content = ShellScope(
      child: IndexedStack(
        index: _openIds.indexOf(_activeId),
        children: [for (final id in _openIds) _panes[id]!],
      ),
    );

    return PopScope<void>(
      canPop: _drawerOpen || (_activeId == 'agent' && _history.isEmpty),
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _goBack();
      },
      child: Scaffold(
        key: _scaffoldKey,
        onDrawerChanged: (open) {
          if (_drawerOpen != open) setState(() => _drawerOpen = open);
        },
        appBar: AppBar(
          title: Text(active.label),
          actions: [
            if (session != null && MediaQuery.sizeOf(context).width >= 720)
              Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Tooltip(
                    message: session.username,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 160),
                      child: Text(
                        session.username,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                ),
              ),
            TextButton(
              key: const Key('logoutButton'),
              onPressed: () async {
                await ref
                    .read(workbenchControllerProvider.notifier)
                    .disconnect();
                if (mounted) {
                  await ref.read(authControllerProvider.notifier).logout();
                }
              },
              child: const Text('退出'),
            ),
          ],
        ),
        drawer: wide ? null : Drawer(child: SafeArea(child: nav)),
        body: wide
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SizedBox(width: 260, child: nav),
                  const VerticalDivider(width: 1),
                  Expanded(child: content),
                ],
              )
            : content,
      ),
    );
  }
}
