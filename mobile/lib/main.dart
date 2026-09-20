import 'package:flutter/material.dart';

import 'screens/home_screen.dart';

void main() {
  runApp(const MedaiApp());
}

class MedaiApp extends StatelessWidget {
  const MedaiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MEDAI',
      theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
      home: const HomeScreen(),
    );
  }
}
