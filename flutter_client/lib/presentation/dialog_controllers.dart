import 'package:flutter/material.dart';

/// Keeps a dialog's text/scroll controllers alive until the route subtree that
/// references them is unmounted.
///
/// Disposing the controllers as soon as `showDialog` returns is too early: the
/// route keeps rebuilding its fields while it animates out, and each rebuild
/// re-subscribes to the controller, which throws "A TextEditingController was
/// used after being disposed". Releasing them from [State.dispose] runs after
/// the fields are gone, so the transition finishes safely.
class DialogControllers extends StatefulWidget {
  const DialogControllers({
    required this.controllers,
    required this.child,
    super.key,
  });

  final List<ChangeNotifier> controllers;
  final Widget child;

  @override
  State<DialogControllers> createState() => _DialogControllersState();
}

class _DialogControllersState extends State<DialogControllers> {
  @override
  void dispose() {
    for (final controller in widget.controllers) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// 弹窗内联错误：主提示加可选细节，避免错误落在会被弹窗遮住的 SnackBar 上。
class DialogErrorNotice extends StatelessWidget {
  const DialogErrorNotice({required this.message, this.detail, super.key});

  final String message;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            message,
            style: TextStyle(
              color: Theme.of(context).colorScheme.error,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (detail != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(detail!, style: Theme.of(context).textTheme.bodySmall),
            ),
        ],
      ),
    );
  }
}
