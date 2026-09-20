import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:medai/main.dart';

void main() {
  testWidgets('MedaiApp boots and shows the placeholder home screen', (WidgetTester tester) async {
    await tester.pumpWidget(const MedaiApp());

    expect(find.text('MEDAI'), findsOneWidget);
    expect(find.byType(Scaffold), findsOneWidget);
  });
}
