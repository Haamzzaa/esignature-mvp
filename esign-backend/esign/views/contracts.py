import logging
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from esign.config import esign_config
from esign.models import Envelope, RepresentativeCandidate
from esign.views.utils import make_rate_limited_response
from services.rate_limiting_service import check_rate_limit, get_client_ip

logger = logging.getLogger(__name__)

class ContractAnalyzeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        is_limited, _, retry_after = check_rate_limit("contract_analyze_ip", ip, esign_config.rate_limit_contract_analysis, "contract_analyze")
        if is_limited:
            return make_rate_limited_response(retry_after)

        import logging

        from rest_framework.exceptions import ValidationError

        from services.recipient_discovery_service import \
            perform_contract_analysis

        logger = logging.getLogger(__name__)

        file_obj = request.data.get('file')
        if not file_obj:
            return Response({"detail": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        
        filename = (file_obj.name or "").lower()
        if not (filename.endswith('.pdf') or filename.endswith('.png') or filename.endswith('.jpg') or filename.endswith('.jpeg')):
            return Response(
                {"detail": "Unsupported file format. Only PDF, PNG, JPG, and JPEG are supported."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Get or resolve envelope_id ────────────────────────────────────
        envelope_id = request.data.get('envelope_id') or request.query_params.get('envelope_id')
        envelope = None
        if envelope_id:
            try:
                envelope = Envelope.objects.get(id=envelope_id)
            except Envelope.DoesNotExist:
                logger.warning(f"Contract analysis failed: Envelope {envelope_id} not found.")
                return Response({"detail": f"Envelope with ID {envelope_id} not found."}, status=status.HTTP_404_NOT_FOUND)
            
            # Check envelope ownership
            if not request.user or not request.user.is_authenticated or envelope.owner != request.user:
                logger.warning(f"Unauthorized contract analysis attempt on envelope {envelope_id} by user {request.user}")
                return Response({"detail": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)

        try:
            file_bytes = file_obj.read()
            response_data = perform_contract_analysis(filename, file_obj.size, file_bytes, envelope=envelope)
            return Response(response_data, status=status.HTTP_200_OK)
        except ValidationError as e:
            detail = e.detail
            if isinstance(detail, list):
                msg = detail[0]
            elif isinstance(detail, dict):
                msg = next(iter(detail.values()))
                if isinstance(msg, list):
                    msg = msg[0]
            else:
                msg = str(detail)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Failed to analyze contract")
            return Response({"detail": "An internal error occurred while processing the document."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfirmCandidatesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, envelope_id, *args, **kwargs):
        from services.recipient_discovery_service import \
            convert_candidate_to_recipient
        
        envelope = get_object_or_404(Envelope, id=envelope_id, owner=request.user)
        candidate_ids = request.data.get("candidate_ids", [])
        
        if not isinstance(candidate_ids, list):
            return Response({"detail": "candidate_ids must be a list of IDs."}, status=status.HTTP_400_BAD_REQUEST)
            
        participants_created = []
        for c_id in candidate_ids:
            try:
                candidate = RepresentativeCandidate.objects.get(id=c_id, envelope=envelope)
                participant = convert_candidate_to_recipient(candidate)
                if participant:
                    participants_created.append(participant)
            except RepresentativeCandidate.DoesNotExist:
                continue
                
        # Return updated list of participants for this envelope
        from esign.serializers import ParticipantSerializer
        participants = envelope.participants.all().order_by('step_number', 'order', 'id')
        serializer = ParticipantSerializer(participants, many=True)
        
        return Response({
            "message": f"Successfully confirmed {len(participants_created)} candidates.",
            "participants": serializer.data
        }, status=status.HTTP_200_OK)


class IgnoreCandidatesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, envelope_id, *args, **kwargs):
        from services.recipient_discovery_service import ignore_candidate
        
        envelope = get_object_or_404(Envelope, id=envelope_id, owner=request.user)
        candidate_ids = request.data.get("candidate_ids", [])
        
        if not isinstance(candidate_ids, list):
            return Response({"detail": "candidate_ids must be a list of IDs."}, status=status.HTTP_400_BAD_REQUEST)
            
        candidates_ignored = []
        for c_id in candidate_ids:
            try:
                candidate = RepresentativeCandidate.objects.get(id=c_id, envelope=envelope)
                ignored_cand = ignore_candidate(candidate)
                if ignored_cand:
                    candidates_ignored.append(ignored_cand.id)
            except RepresentativeCandidate.DoesNotExist:
                continue
                
        return Response({
            "message": f"Successfully ignored {len(candidates_ignored)} candidates.",
            "candidate_ids": candidates_ignored
        }, status=status.HTTP_200_OK)
