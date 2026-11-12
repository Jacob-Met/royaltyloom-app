import unittest, urllib.error
from unittest.mock import patch, Mock
import sandbox_readiness as r
class Tests(unittest.TestCase):
    def setUp(self):
        location=patch.object(r, "_read_private_file", return_value={})
        location.start()
        self.addCleanup(location.stop)
    def test_missing(self):
        with patch.dict('os.environ', {}, clear=True):
            call=Mock()
            self.assertFalse(r.check_authentication(call)['authenticated'])
            call.assert_not_called()
    def test_check(self):
        with patch.dict('os.environ', {'PAYPAL_CLIENT_ID':'private-id','PAYPAL_CLIENT_SECRET':'private-secret'}, clear=True):
            call=Mock(return_value={'access_token':'private-token'})
            result=r.check_authentication(call)
            self.assertTrue(result['authenticated'])
            self.assertNotIn('private-',str(result))
            self.assertTrue(call.call_args.args[0].endswith('/v1/oauth2/token'))
            self.assertEqual(call.call_count,1)
            for response in [{},[],{'access_token':' '}]:
                self.assertFalse(r.check_authentication(Mock(return_value=response))['authenticated'])
            for error in [TimeoutError(),urllib.error.HTTPError('url',401,'private-token',{},None)]:
                result=r.check_authentication(Mock(side_effect=error))
                self.assertFalse(result['authenticated'])
                self.assertNotIn('private-token',str(result))
