import 'package:flutter/material.dart';

import 'conversation_screen.dart';

/// Entry screen. Screens for onboarding/consent/profile/history/allergies/medications
/// (Phase 1) and the rest of ux.screens are added incrementally under lib/screens/ as their
/// backing APIs land — see IMPLEMENTATION_PLAN.md.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('MEDAI')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'MEDAI — Multimodal AI Health Assessment & Clinical Decision Support System\n\n'
                'This is a prototype. It is not a diagnostic system, a prescription service, '
                'or an emergency service.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              // ux.primary_action
              FilledButton.icon(
                icon: const Icon(Icons.mic),
                label: const Text('Talk to Health AI'),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const ConversationScreen()),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
