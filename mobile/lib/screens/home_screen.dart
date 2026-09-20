import 'package:flutter/material.dart';

/// Phase 0 placeholder screen — proves the Flutter skeleton boots.
///
/// Per medai_spec.yaml ux.primary_action, this becomes the "Talk to Health AI"
/// entry point once voice_consultation (Phase 2+) exists. Screens for
/// onboarding/consent/profile/history/allergies/medications (Phase 1) and the
/// rest of ux.screens are added incrementally under lib/screens/ as their
/// backing APIs land — see IMPLEMENTATION_PLAN.md.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('MEDAI')),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(24.0),
          child: Text(
            'MEDAI — Multimodal AI Health Assessment & Clinical Decision Support System\n\n'
            'This is a prototype. It is not a diagnostic system, a prescription service, '
            'or an emergency service.',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}
