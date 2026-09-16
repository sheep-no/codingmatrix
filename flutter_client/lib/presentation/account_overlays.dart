import 'package:flutter/widgets.dart';

/// Dismisses any dialog or bottom sheet opened above [context] while leaving
/// pushed pages untouched.
///
/// An account switch must not leave the previous account's overlay on screen:
/// its actions (delete, rollback, reset) would run with the new account's
/// credentials against the old account's ids.
void closeAccountOverlays(BuildContext context) {
  Navigator.of(context).popUntil((route) => route is! PopupRoute);
}
