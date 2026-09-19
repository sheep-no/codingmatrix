import 'package:flutter/material.dart';

/// Marks a subtree as rendered inside the workbench shell.
///
/// The shell owns the single [AppBar]. A capability page that finds this scope
/// renders only its body, so the window never shows two title bars.
class ShellScope extends InheritedWidget {
  const ShellScope({required super.child, super.key});

  static ShellScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ShellScope>();

  @override
  bool updateShouldNotify(ShellScope oldWidget) => false;
}

/// The scaffold of a capability page.
///
/// Inside the workbench shell it contributes only the body plus a compact
/// action row, because the shell already renders the title bar. Rendered on
/// its own (a widget test, for example) it falls back to a full [Scaffold]
/// with an [AppBar], so pages stay usable and testable standalone.
class ShellScaffold extends StatelessWidget {
  const ShellScaffold({
    required this.title,
    this.actions = const <Widget>[],
    required this.body,
    super.key,
  });

  final String title;
  final List<Widget> actions;
  final Widget body;

  @override
  Widget build(BuildContext context) {
    if (ShellScope.maybeOf(context) == null) {
      return Scaffold(
        appBar: AppBar(title: Text(title), actions: actions),
        body: body,
      );
    }
    if (actions.isEmpty) return body;
    return Column(
      children: [
        Align(
          alignment: Alignment.centerRight,
          child: Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Row(mainAxisSize: MainAxisSize.min, children: actions),
          ),
        ),
        Expanded(child: body),
      ],
    );
  }
}
