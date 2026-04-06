from dj_rest_auth.registration.views import RegisterView


class EmailRegisterView(RegisterView):
    def get_serializer(self, *args, **kwargs):
        data = kwargs.get('data')
        if data is not None:
            mutable_data = data.copy()
            if not mutable_data.get('username') and mutable_data.get('email'):
                mutable_data['username'] = mutable_data['email']
            kwargs['data'] = mutable_data
        return super().get_serializer(*args, **kwargs)
