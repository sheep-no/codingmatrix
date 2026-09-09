import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'application/auth_controller.dart';
import 'presentation/login_page.dart';
import 'presentation/workbench_page.dart';

class CodingMatrixApp extends ConsumerWidget {
  const CodingMatrixApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    return MaterialApp(
      title: 'CodingMatrix Agent',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6D5EF5),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFF0B0D13),
        cardTheme: CardThemeData(
          elevation: 0,
          color: const Color(0xFF151923),
          margin: EdgeInsets.zero,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: Color(0xFF252A38)),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF10131B),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFF2B3140)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFF2B3140)),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFF8B80FF), width: 2),
          ),
        ),
      ),
      home: auth.isRestoring
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : auth.isAuthenticated
          ? const WorkbenchPage()
          : const LoginPage(),
    );
  }
}
